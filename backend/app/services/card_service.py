from __future__ import annotations

import json

from app.database.db import atomic, get_db, now_iso
from app.models.schemas import CardUpdate, KnowledgeEdgeIn, KnowledgeNodeIn
from app.semantic.archimate_mapping import infer_archimate_mapping
from app.services import coherence_service as coherence, graph_service
from app.services.analysis_service import get_card
from app.services.changelog_service import record_change

ROLES = {"objects": ("object", "concerne"), "actions": ("action", "déclenche"),
         "conditions": ("condition", "nécessite"), "tasks": ("task", "se décompose en")}
CONTENT_FIELDS = {"theme_label", "main_effect", "level", "business_category", "business_justification", *ROLES}
JSON_FIELDS = {"main_effect", "objects", "actions", "conditions", "tasks", "suggested_links", "archimate_mapping", "graph_node_ids", "validation_decision"}


def require_card(card_id: str) -> dict:
    card = get_card(card_id)
    if not card:
        raise ValueError("Carte introuvable.")
    return card


def _write_card(card_id: str, values: dict) -> None:
    values = {**values, "updated_at": now_iso()}
    with get_db() as conn:
        conn.execute(f"UPDATE extracted_cards SET {', '.join(f'{key} = ?' for key in values)} WHERE id = ?",
                     [json.dumps(value, ensure_ascii=False) if key in JSON_FIELDS else value for key, value in values.items()] + [card_id])


@atomic
def update_card(card_id: str, update: CardUpdate) -> dict:
    current = require_card(card_id)
    data = update.model_dump(exclude_unset=True)
    if any(value is None for value in data.values()):
        raise ValueError("Une correction ne peut pas contenir de valeur nulle.")
    for role in ROLES:
        if role in data:
            data[role] = list(dict.fromkeys(label.strip() for label in data[role] if label.strip()))
    if "main_effect" in data and not data["main_effect"]["label"].strip():
        raise ValueError("Le concept principal doit avoir un libelle.")
    changed = {key for key in CONTENT_FIELDS if key in data and data[key] != current.get(key)}
    # Only the backend determines validation and mapping transitions.
    for field in ("business_validation_status", "validation_status", "archimate_mapping_status", "ontology_mapping_status", "archimate_mapping"):
        data.pop(field, None)
    status = "to_confirm" if changed else data.get("status", current["status"])
    if status in coherence.VALID_STATUSES:
        from app.services.review_service import diagnostic
        if diagnostic(data.get('main_effect',current['main_effect'])['label']):
            raise ValueError('Une alerte de lecture ne peut pas devenir un concept metier.')
    business = {"accepted": "validated_by_user", "accepted_orphan": "validated_by_user",
                "rejected": "rejected", "to_confirm": "corrected_by_user" if changed else "to_review"}.get(status, "proposed")
    mapping = dict(current.get("archimate_mapping") or {})
    mapping_status = current.get("archimate_mapping_status", "candidate")
    if changed:
        effect = data.get("main_effect", current["main_effect"])
        mapping = infer_archimate_mapping(business_category=data.get("business_category", current["business_category"]),
                                         concept_label=effect["label"], status="inferred_from_user_answer")
        mapping_status = "inferred_from_user_answer"
    elif status in coherence.VALID_STATUSES:
        mapping_status = "candidate"
    elif status in {"rejected", "to_confirm"}:
        mapping_status = "rejected" if status == "rejected" else "to_review"
    mapping["status"] = mapping_status
    data.update(status=status, validation_status=status, business_validation_status=business,
                archimate_mapping=mapping, archimate_mapping_status=mapping_status)
    data["validation_decision"] = {"origin": "user", "status": business, "decided_at": now_iso()}
    if changed:
        data["business_confidence"] = None
    if changed and current.get("ontology_mapping_status") not in {"to_map_later", "unmapped"}:
        data["ontology_mapping_status"] = "to_review"
    if "main_effect" in data or "level" in data:
        effect = {**current["main_effect"], **data.get("main_effect", {})}
        effect["level"] = data.get("level", effect["level"])
        data.update(main_effect=effect, level=effect["level"])
    _write_card(card_id, data)
    updated = require_card(card_id)
    old_ids = _all_card_node_ids(current)
    if changed:
        _synchronize_graph(current, updated)
    elif status in coherence.VALID_STATUSES and not _content_matches(updated):
        _synchronize_graph(current, updated)
    if "suggested_links" in data:
        coherence.save_suggestions({**updated, "suggested_links": data["suggested_links"]})
    if status in coherence.VALID_STATUSES:
        with get_db() as conn:
            conn.execute("""UPDATE knowledge_nodes SET orphan_status = '' WHERE orphan_status = 'orphan_to_review'
                AND id IN (SELECT node_id FROM card_concepts WHERE card_id = ?)""", (card_id,))
    coherence.refresh_states(node_ids=old_ids)
    _sync_mapping_when_exclusive(require_card(card_id))
    record_change(entity_type="card", entity_id=card_id, action="corrected" if changed else status, origin="user",
                  source_id=current["document_id"], details={"before": current, "changed_fields": sorted(changed), "status": status})
    return require_card(card_id)


def _node_for_content(card: dict, role: str, label: str, old_id: str | None, **fields) -> str:
    old = graph_service.get_node(old_id) if old_id else None
    desired = {"label": label, **fields}
    if old and all(old.get(key) == value for key, value in desired.items()):
        return old["id"]
    shared = old and coherence.concept_users(old["id"], excluding=card["id"])
    if old and not shared:
        with get_db() as conn:
            if old["label"] != label:
                graph_service._attach_variant(old["id"], old["label"], "former_label", card["document_id"])
            assignments = ", ".join(f"{key} = ?" for key in desired)
            conn.execute(f"UPDATE knowledge_nodes SET {assignments}, updated_at = ? WHERE id = ?",
                         [json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for value in desired.values()] + [now_iso(), old["id"]])
        return old["id"]
    node_type = "effect" if role == "effect" else "theme" if role == "theme" else ROLES[role][0]
    defaults = graph_service.default_semantic_fields_for_node(node_type=node_type, label=label)
    new = graph_service.create_node(KnowledgeNodeIn(
        type=node_type, source_ids=[card["document_id"]], **{**defaults, **desired},
        metadata={"origin": "correction", "card_id": card["id"], "force_new": bool(old),
                  "derived_from": old["id"] if old else None, "source_excerpt": card.get("source_excerpt", "")},
    ))
    if shared:
        record_change(entity_type="node", entity_id=new["id"], action="local_variant_created", origin="user",
                      source_id=card["document_id"], details={"card_id": card["id"], "original_node_id": old["id"]})
    return new["id"]


def _synchronize_graph(before: dict, card: dict) -> None:
    if 'simple_fields' in card.get('extraction_details', {}):
        from app.services.review_graph import synchronize
        synchronize(before, card)
        return
    old_ids = before.get("graph_node_ids") or {}
    effect = card["main_effect"]
    ids = {"effect": _node_for_content(card, "effect", effect["label"], old_ids.get("effect"),
                                      description=effect["description"], level=card["level"],
                                      business_category=card["business_category"], business_justification=card["business_justification"]),
           "theme": _node_for_content(card, "theme", card["theme_label"], old_ids.get("theme")) if not card.get("extraction_details", {}).get("managed") or card["extraction_details"].get("include_theme") else ""}
    for role in ROLES:
        previous = dict(zip(before[role], old_ids.get(role, [])))
        ids[role] = [_node_for_content(card, role, label, previous.get(label)) for label in card[role]]
    with get_db() as conn:
        old_edges = [row[0] for row in conn.execute("SELECT edge_id FROM card_relations WHERE card_id = ? AND kind = 'structural'", (card["id"],))]
        conn.execute("DELETE FROM card_relations WHERE card_id = ? AND kind = 'structural'", (card["id"],))
        _write_card(card["id"], {"graph_node_ids": ids})
        coherence.bind_concepts({**card, "graph_node_ids": ids})
        for role, relation in [("theme", "concerne"), *[(key, value[1]) for key, value in ROLES.items()]]:
            for target in ids[role] if isinstance(ids[role], list) else [ids[role]]:
                if not target:
                    continue
                edge = graph_service.create_edge(KnowledgeEdgeIn(source_node_id=ids["effect"], target_node_id=target,
                    relation_type=relation, source_ids=[card["document_id"]],
                    metadata={"card_id": card["id"], "origin": "correction"}))
                coherence.bind_relation(card["id"], edge["id"])
        new_ids = set(_all_card_node_ids({"graph_node_ids": ids}))
        replacements = {old_ids.get(role): ids[role] for role in ("effect", "theme") if old_ids.get(role) != ids[role]}
        # Changed endpoints invalidate the decision in this card only.
        for row in conn.execute("SELECT * FROM link_suggestions WHERE card_id = ?", (card["id"],)).fetchall():
            if row["source_node_id"] not in new_ids:
                status = row["status"] if row["status"] in {"ignored", "rejected"} else "to_review"
                conn.execute("UPDATE link_suggestions SET source_node_id = ?, status = ?, updated_at = ? WHERE id = ?",
                             (replacements.get(row["source_node_id"]), status, now_iso(), row["id"]))
        for row in conn.execute("""SELECT e.* FROM knowledge_edges e JOIN card_relations b ON b.edge_id = e.id
                                  WHERE b.card_id = ? AND b.kind = 'manual'""", (card["id"],)).fetchall():
            if row["source_node_id"] not in new_ids:
                conn.execute("DELETE FROM card_relations WHERE card_id = ? AND edge_id = ? AND kind = 'manual'", (card["id"], row["id"]))
                old_edges.append(row["id"])
                record_change(entity_type="edge", entity_id=row["id"], action="detached_after_correction", origin="user", details={"card_id": card["id"]})
        coherence.refresh_states(node_ids=_all_card_node_ids(before), edge_ids=old_edges)


def _content_matches(card: dict) -> bool:
    ids = card.get("graph_node_ids") or {}
    effect = graph_service.get_node(ids.get("effect", ""))
    if not effect or any(effect.get(key) != value for key, value in {
        "label": card["main_effect"]["label"], "description": card["main_effect"]["description"],
        "level": card["level"], "business_category": card["business_category"],
    }.items()):
        return False
    for role in ("theme", *ROLES):
        if role == "theme" and card.get("extraction_details", {}).get("managed") and not card["extraction_details"].get("include_theme"):
            continue
        labels = [card["theme_label"]] if role == "theme" else card[role]
        node_ids = [ids.get(role)] if role == "theme" else ids.get(role, [])
        if len(labels) != len(node_ids):
            return False
        if any(not (node := graph_service.get_node(node_id)) or node["label"] != label for label, node_id in zip(labels, node_ids)):
            return False
    return True


def _sync_mapping_when_exclusive(card: dict) -> None:
    effect_id = card.get("graph_node_ids", {}).get("effect")
    if not effect_id or coherence.concept_users(effect_id, excluding=card["id"]):
        return
    with get_db() as conn:
        conn.execute("""UPDATE knowledge_nodes SET archimate_mapping = ?, archimate_mapping_status = ?,
                     ontology_mapping_status = ? WHERE id = ?""",
                     (json.dumps(card["archimate_mapping"], ensure_ascii=False), card["archimate_mapping_status"], card["ontology_mapping_status"], effect_id))


@atomic
def accept_card(card_id: str, orphan: bool = False) -> dict:
    from app.services.review_service import diagnostic
    if diagnostic(require_card(card_id)['main_effect']['label']):
        raise ValueError('Une alerte de lecture ne peut pas devenir un concept metier.')
    return update_card(card_id, CardUpdate(status="accepted_orphan" if orphan else "accepted"))


@atomic
def detach_concept(card_id: str, node_id: str) -> dict:
    card = require_card(card_id)
    if node_id == card.get("graph_node_ids", {}).get("effect"):
        raise ValueError("Pour retirer le concept principal, supprime la carte ou corrige son contenu.")
    changes = {}
    for role in ROLES:
        ids = card.get("graph_node_ids", {}).get(role, [])
        if node_id in ids:
            changes[role] = [label for label, current_id in zip(card[role], ids) if current_id != node_id]
    if not changes:
        raise ValueError("Concept absent de cette carte.")
    result = update_card(card_id, CardUpdate(**changes))
    record_change(entity_type="card", entity_id=card_id, action="concept_detached", origin="user", details={"node_id": node_id})
    return result


@atomic
def delete_card(card_id: str) -> dict:
    card = require_card(card_id)
    with get_db() as conn:
        edges = [row[0] for row in conn.execute("SELECT edge_id FROM card_relations WHERE card_id = ?", (card_id,))]
        for table in ("card_relations", "card_concepts", "link_suggestions"):
            conn.execute(f"DELETE FROM {table} WHERE card_id = ?", (card_id,))
        conn.execute("DELETE FROM extracted_cards WHERE id = ?", (card_id,))
        conn.execute("UPDATE review_mentions SET status='ignored',card_id='',updated_at=? WHERE card_id=?", (now_iso(),card_id))
        coherence.refresh_states(node_ids=_all_card_node_ids(card), edge_ids=edges)
        record_change(entity_type="card", entity_id=card_id, action="deleted", origin="user",
                      source_id=card["document_id"], details={"before": card})
    return {"deleted_card_id": card_id}


@atomic
def merge_card(source_card_id: str, target_card_id: str) -> dict:
    if source_card_id == target_card_id:
        raise ValueError("Choisis une autre carte.")
    source, target = require_card(source_card_id), require_card(target_card_id)
    if source["status"] in {"linked", "rejected"} or target["status"] in {"linked", "rejected"}:
        raise ValueError("Remets les cartes a revoir avant de les fusionner.")
    changes = {role: list(dict.fromkeys([*target[role], *source[role]])) for role in ROLES}
    from app.services.salience_service import merge_details, key, sync_bindings
    ignored = {(item["role"], key(item["label"])) for item in (target.get("extraction_details") or {}).get("concepts", [])
               if item["importance"] == "ignored" and item.get("origin") == "user"}
    changes = {role: [label for label in labels if (role, key(label)) not in ignored] for role, labels in changes.items()}
    merge_details(source, target)
    result = update_card(target_card_id, CardUpdate(**changes, status="to_confirm"))
    sync_bindings(result)
    # Provenance remains attached even after the source card leaves the active flow.
    with get_db() as conn:
        imported_nodes = {node_id for role in ROLES for label, node_id in zip(result[role], result["graph_node_ids"][role]) if label in source[role]}
        for node_id in imported_nodes:
            graph_service._append_source_to_node(node_id, [source["document_id"]])
        for row in conn.execute("""SELECT e.id, e.target_node_id, e.source_ids FROM knowledge_edges e JOIN card_relations b ON b.edge_id = e.id
                                  WHERE b.card_id = ?""", (target_card_id,)).fetchall():
            if row["target_node_id"] not in imported_nodes:
                continue
            sources = list(dict.fromkeys([*json.loads(row["source_ids"]), source["document_id"]]))
            conn.execute("UPDATE knowledge_edges SET source_ids = ? WHERE id = ?", (json.dumps(sources), row["id"]))
        main_id = source["graph_node_ids"].get("effect")
        transferred = []
        for item in source["suggested_links"]:
            item = {**item}
            if item.get("source_node_id") == main_id:
                item["source_label"] = result["main_effect"]["label"]
            transferred.append(item)
        coherence.save_suggestions({**result, "suggested_links": transferred})
        for original in transferred:
            for candidate in coherence.suggestions_for_card(target_card_id):
                if (candidate["source_label"], candidate.get("target_existing_node_id"), candidate["relation_type"]) == (original["source_label"], original.get("target_existing_node_id"), original["relation_type"]) and candidate["status"] == "proposed":
                    decision = original["status"] if original["status"] in {"ignored", "rejected"} else "to_review"
                    coherence.decide_suggestion(target_card_id, candidate["id"], decision)
    update_card(source_card_id, CardUpdate(status="linked"))
    record_change(entity_type="card", entity_id=target_card_id, action="merged", origin="user",
                  details={"source_card_id": source_card_id, "source_document_id": source["document_id"]})
    return require_card(target_card_id)


def _all_card_node_ids(card: dict) -> list[str]:
    return [node_id for value in (card.get("graph_node_ids") or {}).values()
            for node_id in (value if isinstance(value, list) else [value]) if node_id]
