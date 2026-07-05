from __future__ import annotations

import json
from difflib import SequenceMatcher
import uuid
import unicodedata
from typing import Any

from app.database.db import get_db, now_iso
from app.models.schemas import AliasRequest, KnowledgeEdgeIn, KnowledgeNodeIn
from app.services.changelog_service import record_change
from app.services.serialization import row_to_dict, rows_to_dicts


def create_node(node: KnowledgeNodeIn) -> dict:
    candidates = find_similar_nodes(node.label, node.type)
    exact = next((candidate for candidate in candidates if candidate["match_kind"] == "identical"), None)
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

    close = [candidate for candidate in candidates if candidate["match_kind"] != "identical"]
    if close and not node.metadata.get("force_new"):
        existing = get_node(close[0]["id"])
        if existing:
            _attach_variant(existing["id"], node.label, "variant", (node.source_ids or [None])[0])
            _append_source_to_node(existing["id"], node.source_ids)
            record_change(
                entity_type="node",
                entity_id=existing["id"],
                action="similar_concept_detected",
                origin=str(node.metadata.get("origin", "import")),
                source_id=(node.source_ids or [None])[0],
                details={"incoming_label": node.label, "candidates": close[:5]},
            )
            existing["dedupe"] = {"action": "candidate_found", "candidates": close[:5]}
            return existing

    node_id = str(uuid.uuid4())
    timestamp = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO knowledge_nodes
            (id, label, type, description, level, status, validation_status, confidence,
             created_at, updated_at, source_ids, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    return row_to_dict(row)


def create_edge(edge: KnowledgeEdgeIn) -> dict:
    edge_id = str(uuid.uuid4())
    timestamp = now_iso()
    label = edge.label or edge.relation_type
    with get_db() as conn:
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


def delete_edge(edge_id: str) -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM knowledge_edges WHERE id = ?", (edge_id,)).fetchone()
        if not row:
            raise ValueError("Lien introuvable.")
        edge = row_to_dict(row)
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
    return {"deleted_edge": edge}


def delete_node(node_id: str) -> dict[str, Any]:
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
    params = [status, status, now_iso(), *node_ids]
    with get_db() as conn:
        conn.execute(
            f"""
            UPDATE knowledge_nodes
            SET status = ?, validation_status = ?, updated_at = ?
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


def graph_payload(filter_mode: str = "all", node_id: str | None = None) -> dict[str, Any]:
    nodes = list_nodes()
    edges = list_edges()
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
    nodes = list_nodes()
    edges = list_edges()
    connected = set()
    has_parent = set()
    for edge in edges:
        connected.add(edge["source_node_id"])
        connected.add(edge["target_node_id"])
        if edge["relation_type"] in {"contribue à", "se décompose en"}:
            has_parent.add(edge["source_node_id"])
    orphans = []
    for node in nodes:
        isolated = node["id"] not in connected
        hierarchical_orphan = node["type"] == "effect" and node["id"] not in has_parent
        if isolated or hierarchical_orphan:
            node["orphan_kind"] = "concept isolé" if isolated else "effet sans parent"
            orphans.append(node)
    return orphans


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


def merge_nodes(source_node_id: str, target_node_id: str, note: str = "") -> dict:
    source = get_node(source_node_id)
    target = get_node(target_node_id)
    if not source or not target:
        raise ValueError("Noeud source ou cible introuvable.")
    add_alias(target_node_id, AliasRequest(label=source["label"], kind="former_label"))
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
