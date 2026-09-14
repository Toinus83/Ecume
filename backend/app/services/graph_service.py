from __future__ import annotations

import json
from difflib import SequenceMatcher
import uuid
import unicodedata
from typing import Any

from app.database.db import atomic, get_db, now_iso
from app.models.schemas import AliasRequest, KnowledgeEdgeIn, KnowledgeNodeIn
from app.semantic.archimate_mapping import (
    default_category_for_node_type,
    infer_archimate_mapping,
)
from app.services.changelog_service import record_change
from app.services.serialization import row_to_dict, rows_to_dicts


@atomic
def create_node(node: KnowledgeNodeIn) -> dict:
    if not node.metadata.get("card_id"):
        node = node.model_copy(update={"metadata": {**node.metadata, "standalone_status": node.status}})
    candidates = find_similar_nodes(node.label, node.type)
    exact = next((candidate for candidate in candidates if candidate["match_kind"] == "identical"), None)
    if exact and node.type == "effect":
        existing_effect = get_node(exact["id"])
        if any(existing_effect.get(key) != getattr(node, key) for key in ("description", "level", "business_category")):
            exact = None
    if exact and not node.metadata.get("force_new"):
        _attach_variant(exact["id"], node.label, "variant", (node.source_ids or [None])[0])
        _append_source_to_node(exact["id"], node.source_ids)
        record_change(
            entity_type="node",
            entity_id=exact["id"],
            action="reused_existing_concept",
            origin=str(node.metadata.get("origin", "import")),
            source_id=(node.source_ids or [None])[0],
            details={"incoming_label": node.label, "match_kind": exact["match_kind"]},
        )
        existing = get_node(exact["id"])
        if existing:
            existing["dedupe"] = {"action": "reused_exact", "candidates": candidates}
            return existing

    close = [candidate for candidate in candidates if candidate["match_kind"] != "identical" or not exact]
    node_id = str(uuid.uuid4())
    timestamp = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_nodes
            (id, label, type, description, level, status, validation_status, confidence,
             created_at, updated_at, source_ids, business_category, business_validation_status,
             business_justification, archimate_mapping, archimate_mapping_status,
             ontology_mapping_status, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                node.label,
                node.type,
                node.description,
                node.level,
                node.status,
                node.status,
                node.confidence,
                timestamp,
                timestamp,
                json.dumps(node.source_ids, ensure_ascii=False),
                node.business_category,
                node.business_validation_status,
                node.business_justification,
                json.dumps(
                    node.archimate_mapping.model_dump()
                    if hasattr(node.archimate_mapping, "model_dump")
                    else node.archimate_mapping,
                    ensure_ascii=False,
                ),
                node.archimate_mapping_status,
                node.ontology_mapping_status,
                json.dumps(node.metadata, ensure_ascii=False),
            ),
        )
        row = conn.execute("SELECT * FROM knowledge_nodes WHERE id = ?", (node_id,)).fetchone()
    record_change(
        entity_type="node",
        entity_id=node_id,
        action="created",
        origin=str(node.metadata.get("origin", "import")),
        source_id=(node.source_ids or [None])[0],
        details={"label": node.label, "type": node.type},
    )
    result = row_to_dict(row)
    if close:
        result["dedupe"] = {"action": "candidate_found", "candidates": close[:5]}
    return result


@atomic
def create_edge(edge: KnowledgeEdgeIn) -> dict:
    from app.services.coherence_service import bind_relation
    from app.models.schemas import RelationType
    from typing import get_args
    if edge.relation_type not in get_args(RelationType):
        raise ValueError("Type de relation inconnu.")
    if not get_node(edge.source_node_id) or not get_node(edge.target_node_id):
        raise ValueError("Les deux concepts du lien doivent exister.")
    if edge.source_node_id == edge.target_node_id:
        raise ValueError("Un concept ne peut pas etre relie a lui-meme.")
    edge_id = str(uuid.uuid4())
    timestamp = now_iso()
    label = edge.label or edge.relation_type
    with get_db() as conn:
        existing = conn.execute("""SELECT * FROM knowledge_edges WHERE source_node_id = ?
            AND target_node_id = ? AND relation_type = ? ORDER BY created_at, id LIMIT 1""",
            (edge.source_node_id, edge.target_node_id, edge.relation_type)).fetchone()
        if existing:
            result = row_to_dict(existing)
            source_ids = list(dict.fromkeys([*result["source_ids"], *edge.source_ids]))
            conn.execute("UPDATE knowledge_edges SET source_ids = ? WHERE id = ?", (json.dumps(source_ids), result["id"]))
            result["source_ids"] = source_ids
            if edge.metadata.get("card_id") and not edge.metadata.get("suggestion_id"):
                bind_relation(edge.metadata["card_id"], result["id"], "manual" if edge.metadata.get("origin") == "user" else "structural")
            return result
        conn.execute(
            """
            INSERT INTO knowledge_edges
            (id, source_node_id, target_node_id, relation_type, label, status, confidence,
             created_at, updated_at, source_ids, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge_id,
                edge.source_node_id,
                edge.target_node_id,
                edge.relation_type,
                label,
                edge.status,
                edge.confidence,
                timestamp,
                timestamp,
                json.dumps(edge.source_ids, ensure_ascii=False),
                json.dumps(edge.metadata, ensure_ascii=False),
            ),
        )
        row = conn.execute("SELECT * FROM knowledge_edges WHERE id = ?", (edge_id,)).fetchone()
        if edge.metadata.get("card_id") and not edge.metadata.get("suggestion_id"):
            bind_relation(edge.metadata["card_id"], edge_id, "manual" if edge.metadata.get("origin") == "user" else "structural")
    record_change(
        entity_type="edge",
        entity_id=edge_id,
        action="created",
        origin=str(edge.metadata.get("origin", "import")),
        source_id=(edge.source_ids or [None])[0],
        details={"relation_type": edge.relation_type},
    )
    return row_to_dict(row)


def get_node(node_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM knowledge_nodes WHERE id = ?", (node_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_nodes() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM knowledge_nodes ORDER BY created_at DESC").fetchall()
    return rows_to_dicts(rows)


def list_edges() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM knowledge_edges ORDER BY created_at DESC").fetchall()
    return rows_to_dicts(rows)


@atomic
def delete_edge(edge_id: str) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM knowledge_edges WHERE id = ?", (edge_id,)).fetchone()
        if not row:
            raise ValueError("Lien introuvable.")
        edge = row_to_dict(row)
        metadata = dict(edge["metadata"])
        metadata.pop("standalone_status", None)
        conn.execute("UPDATE knowledge_edges SET metadata = ? WHERE id = ?", (json.dumps(metadata), edge_id))
        contexts = [row[0] for row in conn.execute("SELECT DISTINCT card_id FROM card_relations WHERE edge_id = ?", (edge_id,))]
        conn.execute("DELETE FROM card_relations WHERE edge_id = ?", (edge_id,))
        conn.execute("UPDATE link_suggestions SET status = 'rejected', edge_id = NULL, updated_at = ? WHERE edge_id = ?", (now_iso(), edge_id))
        if contexts:
            for card_id in contexts:
                conn.execute("INSERT INTO card_relations VALUES (?, ?, 'rejected')", (card_id, edge_id))
            conn.execute("UPDATE knowledge_edges SET status = 'rejected', updated_at = ? WHERE id = ?", (now_iso(), edge_id))
        else:
            conn.execute("DELETE FROM knowledge_edges WHERE id = ?", (edge_id,))
    record_change(
        entity_type="edge",
        entity_id=edge_id,
        action="deleted",
        origin="user",
        details={
            "source_node_id": edge["source_node_id"],
            "target_node_id": edge["target_node_id"],
            "relation_type": edge["relation_type"],
        },
    )
    from app.services.coherence_service import refresh_states
    refresh_states(node_ids=[edge["source_node_id"], edge["target_node_id"]], edge_ids=[edge_id])
    return {"deleted_edge": edge}


@atomic
def delete_node(node_id: str) -> dict[str, Any]:
    from app.services.coherence_service import concept_users
    if concept_users(node_id):
        raise ValueError("Concept utilise par une carte : retire-le de ses cartes avant une suppression globale.")
    node = get_node(node_id)
    if not node:
        raise ValueError("Noeud introuvable.")
    with get_db() as conn:
        edge_rows = conn.execute(
            """
            SELECT id FROM knowledge_edges
            WHERE source_node_id = ? OR target_node_id = ?
            """,
            (node_id, node_id),
        ).fetchall()
        edge_ids = [row["id"] for row in edge_rows]
        for edge_id in edge_ids:
            delete_edge(edge_id)
        conn.execute("UPDATE link_suggestions SET status = 'to_review', updated_at = ? WHERE source_node_id = ? OR target_node_id = ?", (now_iso(), node_id, node_id))
        conn.execute(
            "DELETE FROM knowledge_edges WHERE source_node_id = ? OR target_node_id = ?",
            (node_id, node_id),
        )
        conn.execute("DELETE FROM knowledge_node_aliases WHERE node_id = ?", (node_id,))
        conn.execute("DELETE FROM knowledge_nodes WHERE id = ?", (node_id,))
    record_change(
        entity_type="node",
        entity_id=node_id,
        action="deleted",
        origin="user",
        details={
            "label": node["label"],
            "type": node["type"],
            "deleted_edge_ids": edge_ids,
        },
    )
    return {"deleted_node": node, "deleted_edge_ids": edge_ids}


def existing_nodes_for_prompt() -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, label, type, level, status
            FROM knowledge_nodes
            WHERE type IN ('effect', 'object', 'action', 'condition', 'task')
            ORDER BY updated_at DESC
            LIMIT 120
            """
        ).fetchall()
    return rows_to_dicts(rows)


def update_node_status(node_ids: list[str], status: str) -> None:
    if not node_ids:
        return
    placeholders = ",".join("?" for _ in node_ids)
    business_validation_status = _business_validation_from_card_status(status)
    params = [status, status, business_validation_status, now_iso(), *node_ids]
    with get_db() as conn:
        conn.execute(
            f"""
            UPDATE knowledge_nodes
            SET status = ?, validation_status = ?, business_validation_status = ?, updated_at = ?
            WHERE id IN ({placeholders})
            """,
            params,
        )
    for node_id in node_ids:
        record_change(
            entity_type="node",
            entity_id=node_id,
            action="status_updated",
            origin="user",
            details={"status": status},
        )


def default_semantic_fields_for_node(
    *, node_type: str, label: str, document_type: str = "", reason: str = ""
) -> dict[str, Any]:
    business_category = default_category_for_node_type(node_type)
    mapping = infer_archimate_mapping(
        business_category=business_category,
        concept_label=label,
        document_type=document_type,
        reason=reason,
    )
    return {
        "business_category": business_category,
        "business_validation_status": "proposed",
        "business_justification": reason,
        "archimate_mapping": mapping,
        "archimate_mapping_status": mapping["status"],
        "ontology_mapping_status": "to_map_later",
    }


def _business_validation_from_card_status(status: str) -> str:
    if status in {"accepted", "accepted_orphan"}:
        return "validated_by_user"
    if status == "rejected":
        return "rejected"
    if status == "to_confirm":
        return "to_review"
    return "proposed"


def update_card_edges_status(card_id: str, status: str) -> None:
    timestamp = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE knowledge_edges
            SET status = ?, updated_at = ?
            WHERE json_extract(metadata, '$.card_id') = ?
            """,
            (status, timestamp, card_id),
        )
        rows = conn.execute(
            "SELECT id FROM knowledge_edges WHERE json_extract(metadata, '$.card_id') = ?", (card_id,)
        ).fetchall()
    for row in rows:
        record_change(
            entity_type="edge",
            entity_id=row["id"],
            action="status_updated",
            origin="user",
            details={"status": status, "card_id": card_id},
        )


def graph_payload(filter_mode: str = "all", node_id: str | None = None, scope: str = "validated") -> dict[str, Any]:
    nodes = list_nodes()
    edges = list_edges()
    if scope == "validated":
        from app.services.coherence_service import validated_graph
        nodes, edges = validated_graph(nodes, edges)
    node_ids_all = {node["id"] for node in nodes}
    edges = [
        edge
        for edge in edges
        if edge["source_node_id"] in node_ids_all and edge["target_node_id"] in node_ids_all
    ]
    if filter_mode == "effects":
        allowed_types = {"effect"}
    elif filter_mode == "effects_objects":
        allowed_types = {"effect", "object"}
    elif filter_mode == "effects_actions":
        allowed_types = {"effect", "action"}
    elif filter_mode == "orphans":
        orphan_ids = {node["id"] for node in find_orphans()}
        nodes = [node for node in nodes if node["id"] in orphan_ids]
        edges = [edge for edge in edges if edge["source_node_id"] in orphan_ids or edge["target_node_id"] in orphan_ids]
        allowed_types = None
    else:
        allowed_types = None

    if allowed_types:
        nodes = [node for node in nodes if node["type"] in allowed_types]
        node_ids = {node["id"] for node in nodes}
        edges = [
            edge
            for edge in edges
            if edge["source_node_id"] in node_ids and edge["target_node_id"] in node_ids
        ]

    if node_id:
        neighbor_ids = {node_id}
        for edge in edges:
            if edge["source_node_id"] == node_id:
                neighbor_ids.add(edge["target_node_id"])
            if edge["target_node_id"] == node_id:
                neighbor_ids.add(edge["source_node_id"])
        nodes = [node for node in nodes if node["id"] in neighbor_ids]
        edges = [
            edge
            for edge in edges
            if edge["source_node_id"] in neighbor_ids and edge["target_node_id"] in neighbor_ids
        ]

    visible_ids = {node["id"] for node in nodes}
    edges = [edge for edge in edges if edge["source_node_id"] in visible_ids and edge["target_node_id"] in visible_ids]
    return {
        "nodes": nodes,
        "edges": edges,
        "cytoscape": {
            "nodes": [{"data": node} for node in nodes],
            "edges": [
                {
                    "data": {
                        "id": edge["id"],
                        "source": edge["source_node_id"],
                        "target": edge["target_node_id"],
                        "label": edge["label"],
                        **edge,
                    }
                }
                for edge in edges
            ],
        },
    }


def find_orphans() -> list[dict]:
    nodes = [node for node in list_nodes() if node["status"] not in {"rejected", "linked"}]
    edges = list_edges()
    node_ids = {node["id"] for node in nodes}
    connected = set()
    has_parent = set()
    for edge in edges:
        if edge["status"] not in {"accepted", "accepted_orphan"} or not {edge["source_node_id"], edge["target_node_id"]} <= node_ids:
            continue
        connected.add(edge["source_node_id"])
        connected.add(edge["target_node_id"])
        if edge["relation_type"] == "contribue à":
            has_parent.add(edge["source_node_id"])
        elif edge["relation_type"] == "se décompose en":
            has_parent.add(edge["target_node_id"])
    orphans = []
    for node in nodes:
        isolated = node["id"] not in connected
        hierarchical_orphan = node["type"] == "effect" and node["id"] not in has_parent
        if isolated or hierarchical_orphan:
            node["orphan_kind"] = "concept isolé" if isolated else "effet sans parent"
            orphans.append(node)
    from app.services.coherence_service import concept_users
    with get_db() as conn:
        sources = {row["id"]: row["title"] for row in conn.execute("SELECT id, title FROM source_documents UNION ALL SELECT id, title FROM document_references")}
    for node in orphans:
        node["source_titles"] = [sources[item] for item in node["source_ids"] if item in sources]
        node["source_card_ids"] = concept_users(node["id"])
    from app.services.salience_service import node_importance
    importance = node_importance()
    for node in orphans:
        node["importance"] = importance.get(node["id"], "unclassified")
    orphans.sort(key=lambda node: (node["importance"] != "principal", _normalize(node["label"])))
    return orphans


def search_validated_graph(query: str) -> list[dict]:
    from app.services.coherence_service import concept_users, is_valid, validated_graph
    from app.services.analysis_service import get_card
    nodes, edges = validated_graph(list_nodes(), list_edges())
    by_id = {node["id"]: node for node in nodes}
    needle = _normalize(query.strip())
    if not needle:
        return []
    with get_db() as conn:
        aliases = {}
        for row in conn.execute("SELECT node_id, label FROM knowledge_node_aliases"):
            aliases.setdefault(row["node_id"], []).append(row["label"])
    results = []
    for node in sorted(nodes, key=lambda item: _normalize(item["label"])):
        if needle not in _normalize(" ".join([node["label"], node["description"], *aliases.get(node["id"], [])])):
            continue
        neighbors = [{"edge": edge, "node": by_id[edge["target_node_id"] if edge["source_node_id"] == node["id"] else edge["source_node_id"]]}
                     for edge in edges if node["id"] in (edge["source_node_id"], edge["target_node_id"])]
        cards = [card for card_id in concept_users(node["id"]) if (card := get_card(card_id)) and is_valid(card)]
        results.append({"node": node, "neighbors": neighbors, "cards": [{"id": card["id"], "label": card["main_effect"]["label"]} for card in cards]})
        if len(results) >= 50:
            break
    return results



def search_targets(query: str, *, source_id: str = "", document_id: str = "", scope: str = "all",
                   node_type: str = "", offset: int = 0, limit: int = 8) -> dict:
    from app.services.coherence_service import is_valid
    from app.services.salience_service import node_importance
    importance = node_importance()
    needle = _normalize(query.strip())
    if len(needle) < 2:
        return {"items": [], "total": 0, "has_more": False}
    source = get_node(source_id) if source_id else None
    with get_db() as conn:
        aliases = {}
        for row in conn.execute("SELECT node_id, label FROM knowledge_node_aliases"):
            aliases.setdefault(row["node_id"], []).append(row["label"])
        titles = {row["id"]: row["title"] for row in conn.execute(
            "SELECT id, title FROM source_documents UNION SELECT id, title FROM document_references")}
        edges = conn.execute("SELECT source_node_id, target_node_id FROM knowledge_edges WHERE status NOT IN ('rejected', 'linked')").fetchall()
    degree, linked = {}, set()
    for edge in edges:
        for endpoint in edge:
            degree[endpoint] = degree.get(endpoint, 0) + 1
        if source_id in edge:
            linked.update(edge)
    ranked = []
    for node in list_nodes():
        if node["id"] == source_id or node["status"] in {"rejected", "linked"} or (node_type and node["type"] != node_type):
            continue
        valid = is_valid(node)
        same_document = bool(document_id and document_id in node["source_ids"])
        if scope == "validated" and not valid or scope == "document" and not same_document:
            continue
        labels = [_normalize(value) for value in [node["label"], *aliases.get(node["id"], [])]]
        exact = needle in labels
        similarity = max((_similarity(needle, label) for label in labels), default=0)
        contains = any(needle in label for label in labels)
        description = _normalize(node["description"])
        terms = needle.split()
        relevant = exact or contains or similarity >= .55 or all(term in description for term in terms)
        if not relevant or (scope == "close" and not (exact or contains or similarity >= .65)):
            continue
        same_category = bool(source and source["business_category"] == node["business_category"])
        item = {**node, "importance": importance.get(node["id"], "unclassified"), "source_titles": [titles[value] for value in node["source_ids"] if value in titles],
                "already_linked": node["id"] in linked}
        rank = (-int(importance.get(node["id"]) == "principal"), -int(valid), -int(same_document), -int(same_category),
                -int(exact), -int(contains), -round(similarity, 3), -degree.get(node["id"], 0), _normalize(node["label"]), node["id"])
        ranked.append((rank, item))
    ranked.sort(key=lambda item: item[0])
    return {"items": [item for _, item in ranked[offset:offset + limit]], "total": len(ranked),
            "has_more": offset + limit < len(ranked)}

def dashboard_stats() -> dict[str, int]:
    with get_db() as conn:
        documents = conn.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0]
        links = conn.execute("SELECT COUNT(*) FROM knowledge_edges").fetchone()[0]
        counts = {
            row["type"]: row["count"]
            for row in conn.execute(
                "SELECT type, COUNT(*) AS count FROM knowledge_nodes GROUP BY type"
            ).fetchall()
        }
    return {
        "documents": documents,
        "effects": counts.get("effect", 0),
        "objects": counts.get("object", 0),
        "actions": counts.get("action", 0),
        "conditions": counts.get("condition", 0),
        "tasks": counts.get("task", 0),
        "links": links,
        "orphans": len(find_orphans()),
    }


def find_similar_nodes(label: str, node_type: str | None = None) -> list[dict[str, Any]]:
    normalized = _normalize(label)
    if not normalized:
        return []
    with get_db() as conn:
        if node_type:
            rows = conn.execute(
                "SELECT * FROM knowledge_nodes WHERE type = ? ORDER BY updated_at DESC",
                (node_type,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM knowledge_nodes ORDER BY updated_at DESC").fetchall()
        alias_rows = conn.execute("SELECT * FROM knowledge_node_aliases").fetchall()
    aliases_by_node: dict[str, list[str]] = {}
    for alias in alias_rows:
        aliases_by_node.setdefault(alias["node_id"], []).append(alias["label"])

    candidates = []
    for row in rows:
        node = row_to_dict(row)
        labels = [node["label"], *aliases_by_node.get(node["id"], [])]
        best_score = 0.0
        best_label = node["label"]
        for candidate_label in labels:
            score = _similarity(normalized, _normalize(candidate_label))
            if score > best_score:
                best_score = score
                best_label = candidate_label
        if best_score == 1:
            match_kind = "identical"
        elif best_score >= 0.88:
            match_kind = "libellé proche"
        elif best_score >= 0.78 or _token_overlap(normalized, _normalize(best_label)) >= 0.66:
            match_kind = "synonyme probable"
        else:
            continue
        candidates.append(
            {
                "id": node["id"],
                "label": node["label"],
                "type": node["type"],
                "match_label": best_label,
                "score": round(best_score, 3),
                "match_kind": match_kind,
            }
        )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)


@atomic
def add_alias(node_id: str, request: AliasRequest) -> dict:
    if not get_node(node_id):
        raise ValueError("Noeud introuvable.")
    alias_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_node_aliases
            (id, node_id, label, kind, created_at, source_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (alias_id, node_id, request.label, request.kind, now_iso(), request.source_id),
        )
    record_change(
        entity_type="node",
        entity_id=node_id,
        action="alias_added",
        origin="user",
        source_id=request.source_id,
        details={"label": request.label, "kind": request.kind},
    )
    return {"id": alias_id, "node_id": node_id, "label": request.label, "kind": request.kind}


@atomic
def merge_nodes(source_node_id: str, target_node_id: str, note: str = "") -> dict:
    from app.services.coherence_service import concept_users
    if source_node_id == target_node_id:
        raise ValueError("Choisis un autre concept.")
    if concept_users(source_node_id) or concept_users(target_node_id):
        raise ValueError("Fusion globale bloquee : ces concepts sont utilises par des cartes. Utilise la fusion de cartes.")
    source = get_node(source_node_id)
    target = get_node(target_node_id)
    if not source or not target:
        raise ValueError("Noeud source ou cible introuvable.")
    if source["type"] != target["type"]:
        raise ValueError("Les concepts doivent avoir le meme type.")
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM link_suggestions WHERE source_node_id IN (?, ?) OR target_node_id IN (?, ?)",
                        (source_node_id, target_node_id, source_node_id, target_node_id)).fetchone():
            raise ValueError("Des rapprochements utilisent ces concepts. Termine leur traitement avant la fusion globale.")
        if conn.execute("""SELECT 1 FROM card_relations b JOIN knowledge_edges e ON e.id = b.edge_id
                           WHERE e.source_node_id IN (?, ?) OR e.target_node_id IN (?, ?)""",
                        (source_node_id, target_node_id, source_node_id, target_node_id)).fetchone():
            raise ValueError("Des relations de cartes utilisent ces concepts.")
    add_alias(target_node_id, AliasRequest(label=source["label"], kind="former_label"))
    _append_source_to_node(target_node_id, source.get("source_ids", []))
    with get_db() as conn:
        conn.execute(
            "UPDATE knowledge_edges SET source_node_id = ?, updated_at = ? WHERE source_node_id = ?",
            (target_node_id, now_iso(), source_node_id),
        )
        conn.execute(
            "UPDATE knowledge_edges SET target_node_id = ?, updated_at = ? WHERE target_node_id = ?",
            (target_node_id, now_iso(), source_node_id),
        )
        conn.execute(
            """
            UPDATE knowledge_nodes
            SET status = 'linked', validation_status = 'linked', updated_at = ?
            WHERE id = ?
            """,
            (now_iso(), source_node_id),
        )
        conn.execute("UPDATE knowledge_edges SET status = 'rejected' WHERE source_node_id = target_node_id")
        for alias in conn.execute("SELECT * FROM knowledge_node_aliases WHERE node_id = ?", (source_node_id,)).fetchall():
            _attach_variant(target_node_id, alias["label"], alias["kind"], alias["source_id"])
        seen = {}
        for row in conn.execute("SELECT * FROM knowledge_edges ORDER BY created_at, id").fetchall():
            edge = row_to_dict(row)
            if target_node_id not in (edge["source_node_id"], edge["target_node_id"]):
                continue
            key = (edge["source_node_id"], edge["target_node_id"], edge["relation_type"])
            if key in seen:
                canonical = seen[key]
                merged_sources = list(dict.fromkeys([*canonical["source_ids"], *edge["source_ids"]]))
                statuses = (canonical["status"], edge["status"])
                status = next((s for s in ("accepted", "accepted_orphan", "to_confirm", "proposed") if s in statuses), "rejected")
                conn.execute("UPDATE knowledge_edges SET source_ids = ?, status = ? WHERE id = ?", (json.dumps(merged_sources), status, canonical["id"]))
                canonical.update(source_ids=merged_sources, status=status)
                metadata = {**edge["metadata"], "merged_into": canonical["id"]}
                conn.execute("UPDATE knowledge_edges SET status = 'rejected', metadata = ? WHERE id = ?", (json.dumps(metadata), edge["id"]))
            else:
                seen[key] = edge
    record_change(
        entity_type="node",
        entity_id=target_node_id,
        action="merged",
        origin="user",
        details={"source_node_id": source_node_id, "note": note},
    )
    merged = get_node(target_node_id)
    return merged or target


def _attach_variant(node_id: str, label: str, kind: str, source_id: str | None) -> None:
    normalized = _normalize(label)
    with get_db() as conn:
        existing = conn.execute(
            "SELECT label FROM knowledge_node_aliases WHERE node_id = ?", (node_id,)
        ).fetchall()
        if any(_normalize(row["label"]) == normalized for row in existing):
            return
        conn.execute(
            """
            INSERT INTO knowledge_node_aliases
            (id, node_id, label, kind, created_at, source_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), node_id, label, kind, now_iso(), source_id),
        )


def _append_source_to_node(node_id: str, source_ids: list[str]) -> None:
    if not source_ids:
        return
    node = get_node(node_id)
    if not node:
        return
    merged = []
    for source_id in [*node.get("source_ids", []), *source_ids]:
        if source_id and source_id not in merged:
            merged.append(source_id)
    with get_db() as conn:
        conn.execute(
            "UPDATE knowledge_nodes SET source_ids = ?, updated_at = ? WHERE id = ?",
            (json.dumps(merged, ensure_ascii=False), now_iso(), node_id),
        )


def _normalize(value: str) -> str:
    without_accents = "".join(
        char for char in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(char)
    )
    return " ".join(without_accents.replace("'", " ").replace("-", " ").split())


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0
    return SequenceMatcher(None, left, right).ratio()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
