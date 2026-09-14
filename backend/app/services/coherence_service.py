from __future__ import annotations

import hashlib
import json
import uuid

from app.database.db import atomic, get_db, now_iso
from app.services.changelog_service import record_change
from app.services.serialization import row_to_dict

VALID_STATUSES = {"accepted", "accepted_orphan"}
DECISIONS = {"proposed", "accepted", "ignored", "to_review", "rejected"}


def is_valid(entity: dict) -> bool:
    return (entity.get("status") in VALID_STATUSES
            and entity.get("business_validation_status") not in {"rejected", "to_review", "needs_user_validation"}
            and entity.get("orphan_status") != "orphan_to_review")


@atomic
def migrate() -> None:
    with get_db() as conn:
        for statement in [
            "CREATE TABLE IF NOT EXISTS coherence_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)",
            """CREATE TABLE IF NOT EXISTS card_concepts (
                card_id TEXT NOT NULL, node_id TEXT NOT NULL, role TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(card_id, role, position))""",
            "CREATE INDEX IF NOT EXISTS idx_card_concepts_node ON card_concepts(node_id)",
            """CREATE TABLE IF NOT EXISTS card_relations (
                card_id TEXT NOT NULL, edge_id TEXT NOT NULL, kind TEXT NOT NULL,
                PRIMARY KEY(card_id, edge_id, kind))""",
            "CREATE INDEX IF NOT EXISTS idx_card_relations_edge ON card_relations(edge_id)",
            """CREATE TABLE IF NOT EXISTS link_suggestions (
                id TEXT PRIMARY KEY, card_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                source_node_id TEXT, target_node_id TEXT, relation_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed', edge_id TEXT,
                payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(card_id, fingerprint))""",
        ]:
            conn.execute(statement)
        if conn.execute("SELECT 1 FROM coherence_migrations WHERE name = 'bindings_v2'").fetchone():
            return
        upgrading = bool(conn.execute("SELECT 1 FROM coherence_migrations WHERE name = 'bindings_v1'").fetchone())
        cards = [row_to_dict(row) for row in conn.execute("SELECT * FROM extracted_cards")]
        for card in cards:
            bind_concepts(card)
            save_suggestions(card)
            _recover_legacy_card(card)
        for row in conn.execute("SELECT * FROM knowledge_edges").fetchall():
            edge = row_to_dict(row)
            if not conn.execute("SELECT 1 FROM knowledge_nodes WHERE id = ?", (edge["source_node_id"],)).fetchone() or not conn.execute("SELECT 1 FROM knowledge_nodes WHERE id = ?", (edge["target_node_id"],)).fetchone():
                conn.execute("UPDATE knowledge_edges SET status = 'rejected' WHERE id = ?", (edge["id"],))
                record_change(entity_type="edge", entity_id=edge["id"], action="invalid_endpoint", origin="migration", details=edge)
                continue
            if upgrading and conn.execute("SELECT 1 FROM card_relations WHERE edge_id = ?", (edge["id"],)).fetchone():
                continue
            card_id = edge.get("metadata", {}).get("card_id")
            if not any(card["id"] == card_id for card in cards):
                continue
            suggestion = conn.execute(
                """SELECT id FROM link_suggestions WHERE card_id = ?
                AND target_node_id = ? AND relation_type = ?""",
                (card_id, edge["target_node_id"], edge["relation_type"]),
            ).fetchone()
            kind = "legacy_suggestion" if suggestion else "structural"
            conn.execute("INSERT OR IGNORE INTO card_relations VALUES (?, ?, ?)", (card_id, edge["id"], kind))
            if suggestion:
                conn.execute("UPDATE link_suggestions SET edge_id = ?, status = 'to_review' WHERE id = ?", (edge["id"], suggestion["id"]))
                conn.execute("UPDATE knowledge_edges SET status = 'to_confirm' WHERE id = ?", (edge["id"],))
        refresh_states()
        conn.execute("INSERT OR IGNORE INTO coherence_migrations VALUES ('bindings_v1', ?)", (now_iso(),))
        conn.execute("INSERT INTO coherence_migrations VALUES ('bindings_v2', ?)", (now_iso(),))
        record_change(entity_type="system", entity_id="bindings_v2", action="migrated", origin="migration",
                      details={"cards": len(cards), "note": "Legacy link suggestions require an explicit decision."})


def bind_concepts(card: dict) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM card_concepts WHERE card_id = ?", (card["id"],))
        missing = []
        for role, values in (card.get("graph_node_ids") or {}).items():
            for position, node_id in enumerate(values if isinstance(values, list) else [values]):
                if not node_id:
                    continue
                if conn.execute("SELECT 1 FROM knowledge_nodes WHERE id = ?", (node_id,)).fetchone():
                    conn.execute("INSERT INTO card_concepts VALUES (?, ?, ?, ?)", (card["id"], node_id, role, position))
                else:
                    missing.append(node_id)
        if missing and card["status"] not in {"rejected", "linked"}:
            conn.execute("""UPDATE extracted_cards SET status = 'to_confirm', validation_status = 'to_confirm',
                         business_validation_status = 'to_review' WHERE id = ?""", (card["id"],))
            record_change(entity_type="card", entity_id=card["id"], action="missing_references", origin="migration",
                          details={"node_ids": missing})


    from app.services.salience_service import sync_bindings
    sync_bindings(card)


def concept_users(node_id: str, excluding: str | None = None) -> list[str]:
    with get_db() as conn:
        return [row[0] for row in conn.execute(
            """SELECT card_id FROM card_concepts WHERE node_id = ? AND card_id != ?
               UNION SELECT b.card_id FROM card_relations b JOIN knowledge_edges e ON e.id = b.edge_id
               WHERE (e.source_node_id = ? OR e.target_node_id = ?) AND b.card_id != ?""",
            (node_id, excluding or "", node_id, node_id, excluding or ""),
        )]


def bind_relation(card_id: str, edge_id: str, kind: str = "structural") -> None:
    with get_db() as conn:
        suppressed = conn.execute("SELECT 1 FROM card_relations WHERE card_id = ? AND edge_id = ? AND kind = 'rejected'", (card_id, edge_id)).fetchone()
        if suppressed:
            if kind == "structural":
                return
            conn.execute("DELETE FROM card_relations WHERE card_id = ? AND edge_id = ? AND kind = 'rejected'", (card_id, edge_id))
        conn.execute("INSERT OR IGNORE INTO card_relations VALUES (?, ?, ?)", (card_id, edge_id, kind))


def save_suggestions(card: dict) -> None:
    from app.services.graph_service import _normalize
    with get_db() as conn:
        bindings = conn.execute("""SELECT b.node_id, n.label FROM card_concepts b
                                JOIN knowledge_nodes n ON n.id = b.node_id WHERE b.card_id = ?""", (card["id"],)).fetchall()
        for item in card.get("suggested_links", []):
            if not isinstance(item, dict):
                continue
            source_label = item.get("source_label", "")
            matches = {row["node_id"] for row in bindings if _normalize(row["label"]) == _normalize(source_label)}
            # Resolve against the card's labels too, including reused aliases.
            for role, values in card.get("graph_node_ids", {}).items():
                labels = ([card["main_effect"]["label"]] if role == "effect" else
                          [card["theme_label"]] if role == "theme" else card.get(role, []))
                for label, node_id in zip(labels, values if isinstance(values, list) else [values]):
                    if _normalize(label) == _normalize(source_label):
                        matches.add(node_id)
            source_id = next(iter(matches)) if len(matches) == 1 else None
            target_id = item.get("target_existing_node_id")
            relation = item.get("relation_type") or "proche de"
            fingerprint = hashlib.sha256(json.dumps([_normalize(source_label), target_id, relation], ensure_ascii=False).encode()).hexdigest()
            timestamp = now_iso()
            conn.execute("""INSERT OR IGNORE INTO link_suggestions
                (id, card_id, fingerprint, source_node_id, target_node_id, relation_type, status, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?)""",
                (str(uuid.uuid4()), card["id"], fingerprint, source_id, target_id, relation,
                 json.dumps(item, ensure_ascii=False), timestamp, timestamp))


def suggestions_for_card(card_id: str) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM link_suggestions WHERE card_id = ? ORDER BY created_at, id", (card_id,)).fetchall()
        return [{**json.loads(row["payload"]), "id": row["id"], "status": row["status"],
             "source_node_id": row["source_node_id"], "target_existing_node_id": row["target_node_id"],
             "edge_id": row["edge_id"], "created_at": row["created_at"], "updated_at": row["updated_at"],
             **suggestion_availability(conn, row)} for row in rows]


def suggestion_availability(conn, row) -> dict:
    from typing import get_args
    from app.models.schemas import RelationType
    card = conn.execute("SELECT status FROM extracted_cards WHERE id = ?", (row["card_id"],)).fetchone()
    source = conn.execute("SELECT status FROM knowledge_nodes WHERE id = ?", (row["source_node_id"],)).fetchone()
    target = conn.execute("SELECT status, label FROM knowledge_nodes WHERE id = ?", (row["target_node_id"],)).fetchone()
    reason = ""
    if not card or card["status"] in {"rejected", "linked"}:
        reason = "Carte rejetee ou fusionnee : remettre la carte a revoir."
    elif not source or not conn.execute("SELECT 1 FROM card_concepts WHERE card_id = ? AND node_id = ?",
                                        (row["card_id"], row["source_node_id"])).fetchone():
        reason = "Lien incomplet : le concept source doit etre retrouve dans la carte."
    elif source["status"] in {"rejected", "linked"}:
        reason = "Lien a revoir : le concept source est rejete ou fusionne."
    elif not target:
        reason = "Lien incomplet : le concept cible est introuvable. Choisissez une nouvelle cible."
    elif target["status"] in {"rejected", "linked"}:
        reason = "Lien a revoir : le concept cible est rejete ou fusionne. Choisissez une nouvelle cible."
    elif row["source_node_id"] == row["target_node_id"]:
        reason = "Lien a revoir : la source et la cible designent le meme concept."
    elif row["relation_type"] not in get_args(RelationType):
        reason = "Lien a revoir : le type de relation doit etre corrige."
    return {"can_accept": not reason, "invalid_reason": reason,
            **({"target_label": target["label"]} if target else {})}


@atomic
def repair_suggestion(card_id: str, suggestion_id: str, correction) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM link_suggestions WHERE id = ? AND card_id = ?", (suggestion_id, card_id)).fetchone()
        if not row or row["status"] not in {"proposed", "to_review"}:
            raise ValueError("Ce rapprochement n'est plus dans la file de correction. Actualisez la carte.")
        conn.execute("""UPDATE link_suggestions SET source_node_id = ?, target_node_id = ?, relation_type = ?,
                     status = 'to_review', updated_at = ? WHERE id = ?""",
                     (correction.source_node_id, correction.target_node_id, correction.relation_type, now_iso(), suggestion_id))
        changed = conn.execute("SELECT * FROM link_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        availability = suggestion_availability(conn, changed)
        if not availability["can_accept"]:
            raise ValueError(availability["invalid_reason"])
        source = conn.execute("SELECT label FROM knowledge_nodes WHERE id = ?", (correction.source_node_id,)).fetchone()
        payload = {**json.loads(row["payload"]), "source_label": source["label"],
                   "target_label": availability["target_label"], "relation_type": correction.relation_type,
                   "business_confidence": None, "validation_decision": {"origin": "user", "action": "corrected", "decided_at": now_iso()}}
        conn.execute("UPDATE link_suggestions SET payload = ? WHERE id = ?", (json.dumps(payload), suggestion_id))
        refresh_states(edge_ids=[row["edge_id"]] if row["edge_id"] else [])
        record_change(entity_type="suggestion", entity_id=suggestion_id, action="corrected", origin="user",
                      details={"before": dict(row), "correction": correction.model_dump()})
    return next(item for item in suggestions_for_card(card_id) if item["id"] == suggestion_id)


@atomic
def create_suggestion_target(card_id: str, suggestion_id: str, request) -> dict:
    from app.models.schemas import KnowledgeNodeIn, SuggestionRepair
    from app.services import card_service, graph_service
    card = card_service.require_card(card_id)
    label = request.label.strip()
    if not label:
        raise ValueError("Donnez un libelle au concept.")
    candidates = graph_service.find_similar_nodes(label)
    existing = [graph_service.get_node(candidate["id"]) for candidate in candidates]
    if any(node and node["status"] not in {"rejected", "linked"} for node in existing):
        raise ValueError("Un concept similaire existe deja. Recherchez-le et choisissez une cible existante avant de creer un doublon.")
    node = graph_service.create_node(KnowledgeNodeIn(
        label=label, type=request.type, description=request.description, status="to_confirm",
        business_validation_status="to_review", source_ids=[card["document_id"]],
        metadata={"origin": "user", "source_excerpt": card.get("source_excerpt", ""), "suggestion_id": suggestion_id,
                  "force_new": bool(candidates)},
    ))
    # Creation and repair roll back together if the suggestion became unavailable.
    return repair_suggestion(card_id, suggestion_id, SuggestionRepair(
        source_node_id=request.source_node_id, target_node_id=node["id"], relation_type=request.relation_type,
    ))


@atomic
def decide_suggestion(card_id: str, suggestion_id: str, status: str, *, automatic_decision: dict | None = None) -> dict:
    from app.models.schemas import KnowledgeEdgeIn
    from app.services import graph_service
    if status not in DECISIONS:
        raise ValueError("Decision de rapprochement invalide.")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM link_suggestions WHERE id = ? AND card_id = ?", (suggestion_id, card_id)).fetchone()
        if not row:
            raise ValueError("Rapprochement introuvable.")
        card_row = conn.execute("SELECT * FROM extracted_cards WHERE id = ?", (card_id,)).fetchone()
        if not card_row:
            raise ValueError("Carte introuvable.")
        card = row_to_dict(card_row)
        edge_id = row["edge_id"]
        if status == "accepted":
            availability = suggestion_availability(conn, row)
            if not availability["can_accept"]:
                # A stale browser receives a reviewable suggestion, never a low-level edge error.
                conn.execute("UPDATE link_suggestions SET status = 'to_review', updated_at = ? WHERE id = ?",
                             (now_iso(), suggestion_id))
                refresh_states(edge_ids=[edge_id] if edge_id else [])
                record_change(entity_type="suggestion", entity_id=suggestion_id, action="acceptance_blocked",
                              origin="system", details={"reason": availability["invalid_reason"]})
                return next(item for item in suggestions_for_card(card_id) if item["id"] == suggestion_id)
            payload = json.loads(row["payload"])
            confidence = payload.get("confidence", "medium")
            if not isinstance(confidence, str) or confidence not in {"low", "medium", "high"}:
                confidence = "medium"
            edge = graph_service.create_edge(KnowledgeEdgeIn(
                source_node_id=row["source_node_id"], target_node_id=row["target_node_id"] or "",
                relation_type=row["relation_type"], status="to_confirm", source_ids=[card["document_id"]],
                confidence=confidence,
                metadata={"origin": "validation_policy" if automatic_decision else "user", "reason": payload.get("reason", ""), "card_id": card_id, "suggestion_id": suggestion_id},
            ))
            edge_id = edge["id"]
            bind_relation(card_id, edge_id, "suggestion")
        conn.execute("UPDATE link_suggestions SET status = ?, edge_id = ?, updated_at = ? WHERE id = ?",
                     (status, edge_id, now_iso(), suggestion_id))
        payload = json.loads(row["payload"])
        payload["validation_decision"] = automatic_decision or {"origin": "user", "status": status, "decided_at": now_iso()}
        conn.execute("UPDATE link_suggestions SET payload = ? WHERE id = ?", (json.dumps(payload), suggestion_id))
        refresh_states(edge_ids=[edge_id] if edge_id else [])
        record_change(entity_type="suggestion", entity_id=suggestion_id, action=status, origin="validation_policy" if automatic_decision else "user",
                      source_id=card["document_id"], details={"card_id": card_id, "before": row["status"], "edge_id": edge_id, "decision": payload["validation_decision"]})
    return next(item for item in suggestions_for_card(card_id) if item["id"] == suggestion_id)


def refresh_states(node_ids: list[str] | None = None, edge_ids: list[str] | None = None) -> None:
    with get_db() as conn:
        nodes = {row[0] for row in conn.execute("SELECT DISTINCT node_id FROM card_concepts")}
        for row in conn.execute("SELECT e.source_node_id, e.target_node_id FROM knowledge_edges e JOIN card_relations b ON b.edge_id = e.id"):
            nodes.update(row)
        nodes.update(node_ids or [])
        for edge_id in edge_ids or []:
            endpoints = conn.execute("SELECT source_node_id, target_node_id FROM knowledge_edges WHERE id = ?", (edge_id,)).fetchone()
            if endpoints:
                nodes.update(endpoints)
        for node_id in nodes:
            cards = [dict(row) for row in conn.execute("""SELECT DISTINCT c.id, c.status, c.business_validation_status, c.business_confidence, c.validation_decision
                FROM extracted_cards c JOIN card_concepts b ON b.card_id = c.id WHERE b.node_id = ?""", (node_id,))]
            cards.extend(dict(row) for row in conn.execute("""SELECT DISTINCT c.id, c.status, c.business_validation_status, c.business_confidence, c.validation_decision
                FROM extracted_cards c JOIN card_relations b ON b.card_id = c.id JOIN knowledge_edges e ON e.id = b.edge_id
                WHERE (e.source_node_id = ? OR e.target_node_id = ?) AND
                (b.kind = 'manual' OR (b.kind IN ('suggestion', 'legacy_suggestion') AND EXISTS
                  (SELECT 1 FROM link_suggestions s WHERE s.card_id = c.id AND s.edge_id = e.id AND s.status = 'accepted')))""", (node_id, node_id)))
            node_row = conn.execute("SELECT metadata FROM knowledge_nodes WHERE id = ?", (node_id,)).fetchone()
            if node_row:
                standalone = json.loads(node_row["metadata"]).get("standalone_status")
                if standalone:
                    cards.append({"status": standalone})
            status = aggregate_status(cards)
            business, confidence, decision = aggregate_validation(cards, status)
            conn.execute("UPDATE knowledge_nodes SET status = ?, validation_status = ?, business_validation_status = ?, business_confidence = ?, validation_decision = ?, updated_at = ? WHERE id = ?",
                         (status, status, business, confidence, json.dumps(decision), now_iso(), node_id))
            if status == "accepted":
                validated = conn.execute("""SELECT c.archimate_mapping, c.archimate_mapping_status, c.ontology_mapping_status
                    FROM extracted_cards c JOIN card_concepts b ON b.card_id = c.id
                    WHERE b.node_id = ? AND b.role = 'effect' AND c.status IN ('accepted', 'accepted_orphan')
                    AND c.business_validation_status NOT IN ('rejected', 'to_review') ORDER BY c.updated_at DESC LIMIT 1""", (node_id,)).fetchone()
                if validated:
                    conn.execute("UPDATE knowledge_nodes SET archimate_mapping = ?, archimate_mapping_status = ?, ontology_mapping_status = ? WHERE id = ?",
                                 (*validated, node_id))
        edges = {row[0] for row in conn.execute("SELECT DISTINCT edge_id FROM card_relations")}
        edges.update(edge_ids or [])
        for edge_id in edges:
            contexts = []
            for row in conn.execute("""SELECT c.id, c.status, c.business_validation_status, c.business_confidence, c.validation_decision, b.kind
                FROM extracted_cards c JOIN card_relations b ON c.id = b.card_id WHERE b.edge_id = ?""", (edge_id,)):
                context = dict(row)
                if row["kind"] == "rejected":
                    context["status"] = "rejected"
                if row["kind"] in {"suggestion", "legacy_suggestion"}:
                    suggestions = conn.execute("SELECT status, payload FROM link_suggestions WHERE card_id = ? AND edge_id = ?", (row["id"], edge_id)).fetchall()
                    decisions = [r["status"] for r in suggestions]
                    if "accepted" not in decisions:
                        context["status"] = "to_confirm" if any(s in {"proposed", "to_review"} for s in decisions) or not decisions else "rejected"
                    else:
                        evidence = [json.loads(r["payload"]).get("validation_decision", {}) for r in suggestions if r["status"] == "accepted"]
                        choice = next((item for item in evidence if item.get("origin") != "validation_policy"), evidence[0])
                        context["business_validation_status"] = "auto_validated" if choice.get("origin") == "validation_policy" else "validated_by_user"
                        context["business_confidence"] = choice.get("score")
                        context["validation_decision"] = json.dumps(choice)
                elif row["kind"] == "manual" and is_valid(context):
                    context["business_validation_status"] = "validated_by_user"
                contexts.append(context)
            metadata_row = conn.execute("SELECT metadata FROM knowledge_edges WHERE id = ?", (edge_id,)).fetchone()
            if metadata_row:
                standalone = json.loads(metadata_row["metadata"]).get("standalone_status")
                if standalone:
                    contexts.append({"status": standalone, "business_validation_status": "validated_by_user"})
            status = aggregate_status(contexts)
            edge = conn.execute("SELECT source_node_id, target_node_id FROM knowledge_edges WHERE id = ?", (edge_id,)).fetchone()
            if edge and (edge[0] == edge[1] or any(not conn.execute("SELECT 1 FROM knowledge_nodes WHERE id = ?", (node_id,)).fetchone() for node_id in edge)):
                status = "rejected"
            business, confidence, decision = aggregate_validation(contexts, status)
            conn.execute("UPDATE knowledge_edges SET status = ?, business_validation_status = ?, business_confidence = ?, validation_decision = ?, updated_at = ? WHERE id = ?",
                         (status, business, confidence, json.dumps(decision), now_iso(), edge_id))


def aggregate_validation(contexts: list[dict], status: str) -> tuple:
    valid = [item for item in contexts if is_valid(item)]
    if status == "accepted" and valid:
        chosen = next((item for item in valid if item.get("business_validation_status") != "auto_validated"), valid[0])
        business = "auto_validated" if chosen.get("business_validation_status") == "auto_validated" else "validated_by_user"
        evidence = chosen.get("validation_decision") or "{}"
        evidence = json.loads(evidence) if isinstance(evidence, str) else evidence
        return business, chosen.get("business_confidence"), {**evidence, "supporting_card_ids": sorted({item["id"] for item in valid if item.get("id")})}
    return ("rejected" if status == "rejected" else "to_review" if status == "to_confirm" else "proposed"), None, {}


def aggregate_status(contexts: list[dict]) -> str:
    if any(is_valid(item) for item in contexts):
        return "accepted"
    if any(item["status"] == "to_confirm" for item in contexts):
        return "to_confirm"
    if any(item["status"] == "proposed" for item in contexts):
        return "proposed"
    return "rejected"


def validated_graph(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    nodes = [node for node in nodes if is_valid(node)]
    node_ids = {node["id"] for node in nodes}
    unique = {}
    for edge in sorted(edges, key=lambda item: (item["created_at"], item["id"])):
        source, target = edge["source_node_id"], edge["target_node_id"]
        if is_valid(edge) and source in node_ids and target in node_ids and source != target:
            unique.setdefault((source, target, edge["relation_type"]), edge)
    return nodes, list(unique.values())


def _recover_legacy_card(card: dict) -> None:
    ids = card.get("graph_node_ids") or {}
    with get_db() as conn:
        main = conn.execute("SELECT * FROM knowledge_nodes WHERE id = ?", (ids.get("effect", ""),)).fetchone()
        mismatch = not main or any(main[key] != expected for key, expected in {
            "label": card["main_effect"]["label"], "description": card["main_effect"].get("description", ""),
            "level": card["level"], "business_category": card["business_category"],
        }.items())
        for role, relation in (("theme", "concerne"), ("objects", "concerne"), ("actions", "déclenche"),
                               ("conditions", "nécessite"), ("tasks", "se décompose en")):
            targets = ids.get(role, [])
            targets = targets if isinstance(targets, list) else [targets]
            labels = [card["theme_label"]] if role == "theme" else card[role]
            if len(labels) != len(targets):
                mismatch = True
            for label, target in zip(labels, targets):
                node = conn.execute("SELECT label FROM knowledge_nodes WHERE id = ?", (target,)).fetchone()
                if not node or node["label"] != label:
                    mismatch = True
                for edge in conn.execute("SELECT id FROM knowledge_edges WHERE source_node_id = ? AND target_node_id = ? AND relation_type = ?",
                                         (ids.get("effect", ""), target, relation)):
                    bind_relation(card["id"], edge["id"])
        if mismatch and card["status"] in VALID_STATUSES:
            conn.execute("UPDATE extracted_cards SET status = 'to_confirm', validation_status = 'to_confirm', business_validation_status = 'to_review' WHERE id = ?", (card["id"],))
            record_change(entity_type="card", entity_id=card["id"], action="legacy_content_to_review", origin="migration",
                          details={"note": "Existing card and graph disagree; original content is preserved."})
