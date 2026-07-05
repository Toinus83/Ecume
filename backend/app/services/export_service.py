from __future__ import annotations

import csv
import json
from pathlib import Path
import zipfile

from app.config import EXPORT_DIR
from app.database.db import get_db, now_iso
from app.services.serialization import row_to_dict, rows_to_dicts


RELATION_DESCRIPTIONS = {
    "contribue à": "Le concept source participe à l'atteinte du concept cible.",
    "se décompose en": "Le concept source est détaillé par le concept cible.",
    "concerne": "Le concept source porte sur le concept cible.",
    "nécessite": "Le concept source requiert le concept cible.",
    "déclenche": "Le concept source active ou entraîne le concept cible.",
    "proche de": "Les deux concepts sont proches, sans équivalence stricte confirmée.",
    "équivalent à": "Les deux concepts désignent la même notion métier.",
}


def export_json() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / "ecume_export.json"
    payload = _complete_export_payload()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_jsonld() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / "ecume_export.jsonld"
    payload = _complete_export_payload()
    jsonld = {
        "@context": {
            "ecume": "urn:ecume:vocab:",
            "id": "@id",
            "type": "@type",
            "label": "ecume:label",
            "canonicalLabel": "ecume:canonicalLabel",
            "aliases": "ecume:aliases",
            "description": "ecume:description",
            "level": "ecume:level",
            "status": "ecume:status",
            "confidence": "ecume:confidence",
            "sourceDocuments": {"@id": "ecume:sourceDocuments", "@type": "@id"},
            "source": {"@id": "ecume:source", "@type": "@id"},
            "target": {"@id": "ecume:target", "@type": "@id"},
            "relationType": "ecume:relationType",
            "direction": "ecume:direction",
            "createdAt": "ecume:createdAt",
            "updatedAt": "ecume:updatedAt",
        },
        "@graph": [],
    }
    jsonld["@graph"].extend(
        {
            "@id": f"urn:ecume:document:{doc['id']}",
            "@type": "ecume:SourceDocument",
            "label": doc["title"],
            "filename": doc["filename"],
            "fileType": doc["file_type"],
            "createdAt": doc["created_at"],
            "metadata": doc["metadata"],
        }
        for doc in payload["documents"]
    )
    jsonld["@graph"].extend(
        {
            "@id": f"urn:ecume:node:{node['id']}",
            "@type": f"ecume:{node['type']}",
            "label": node["label"],
            "canonicalLabel": node["canonical_label"],
            "aliases": node["aliases"],
            "description": node["description"],
            "level": node["level"],
            "status": node["status"],
            "confidence": node["confidence"],
            "sourceDocuments": [
                f"urn:ecume:document:{source_id}" for source_id in node["source_ids"]
            ],
            "sourceTitles": node["source_titles"],
            "createdAt": node["created_at"],
            "updatedAt": node["updated_at"],
            "metadata": node["metadata"],
        }
        for node in payload["nodes"]
    )
    jsonld["@graph"].extend(
        {
            "@id": f"urn:ecume:edge:{edge['id']}",
            "@type": "ecume:Relation",
            "label": edge["label"],
            "description": edge["description"],
            "relationType": edge["relation_type"],
            "direction": edge["direction"],
            "source": f"urn:ecume:node:{edge['source_node_id']}",
            "sourceLabel": edge["source_label"],
            "target": f"urn:ecume:node:{edge['target_node_id']}",
            "targetLabel": edge["target_label"],
            "status": edge["status"],
            "confidence": edge["confidence"],
            "sourceDocuments": [
                f"urn:ecume:document:{source_id}" for source_id in edge["source_ids"]
            ],
            "sourceTitles": edge["source_titles"],
            "createdAt": edge["created_at"],
            "updatedAt": edge["updated_at"],
            "metadata": edge["metadata"],
        }
        for edge in payload["edges"]
    )
    path.write_text(json.dumps(jsonld, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_csv_bundle() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = _complete_export_payload()
    nodes_path = EXPORT_DIR / "nodes.csv"
    edges_path = EXPORT_DIR / "edges.csv"
    documents_path = EXPORT_DIR / "documents.csv"
    cards_path = EXPORT_DIR / "cards.csv"
    _write_nodes(nodes_path, payload["nodes"])
    _write_edges(edges_path, payload["edges"])
    _write_documents(documents_path, payload["documents"])
    _write_cards(cards_path, payload["cards"])
    zip_path = EXPORT_DIR / "ecume_csv_export.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(nodes_path, arcname="nodes.csv")
        bundle.write(edges_path, arcname="edges.csv")
        bundle.write(documents_path, arcname="documents.csv")
        bundle.write(cards_path, arcname="cards.csv")
    return zip_path


def export_memgraph_bundle() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = _complete_export_payload()
    nodes_path = EXPORT_DIR / "memgraph_nodes.csv"
    edges_path = EXPORT_DIR / "memgraph_edges.csv"
    cypher_path = EXPORT_DIR / "memgraph_import.cypher"
    _write_nodes(nodes_path, payload["nodes"])
    _write_edges(edges_path, payload["edges"])
    cypher_path.write_text(_memgraph_cypher(), encoding="utf-8")
    zip_path = EXPORT_DIR / "ecume_memgraph_export.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(nodes_path, arcname="memgraph_nodes.csv")
        bundle.write(edges_path, arcname="memgraph_edges.csv")
        bundle.write(cypher_path, arcname="memgraph_import.cypher")
    return zip_path


def export_rdf_skos_skeleton() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / "ecume_skos_skeleton.ttl"
    payload = _complete_export_payload()
    lines = [
        "@prefix ecume: <urn:ecume:vocab:> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "",
    ]
    for node in payload["nodes"]:
        uri = f"<urn:ecume:node:{node['id']}>"
        lines.extend(
            [
                f"{uri} a skos:Concept ;",
                f'  skos:prefLabel "{_ttl_escape(node["canonical_label"])}" ;',
                *[
                    f'  skos:altLabel "{_ttl_escape(alias["label"])}" ;'
                    for alias in node["aliases"]
                ],
                f'  skos:definition "{_ttl_escape(node["description"] or node["label"])}" ;',
                f'  ecume:type "{node["type"]}" ;',
                f'  ecume:level "{node["level"]}" ;',
                f'  ecume:status "{node["status"]}" .',
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _complete_export_payload() -> dict:
    documents = _list_documents()
    cards = _list_cards()
    nodes = _list_nodes()
    edges = _list_edges()
    changelog = _list_changelog()
    aliases_by_node = _aliases_by_node()
    doc_by_id = {doc["id"]: doc for doc in documents}
    node_by_id = {node["id"]: node for node in nodes}
    card_by_id = {card["id"]: card for card in cards}

    enriched_nodes = [
        _enrich_node(node, aliases_by_node.get(node["id"], []), doc_by_id, card_by_id)
        for node in nodes
    ]
    enriched_edges = [_enrich_edge(edge, node_by_id, doc_by_id, card_by_id) for edge in edges]
    enriched_cards = [_enrich_card(card, doc_by_id) for card in cards]
    return {
        "export_metadata": {
            "format": "ECUME complete knowledge export",
            "version": "0.2.0",
            "generated_at": now_iso(),
            "relation_types": RELATION_DESCRIPTIONS,
            "stable_uri_patterns": {
                "node": "urn:ecume:node:{id}",
                "edge": "urn:ecume:edge:{id}",
                "document": "urn:ecume:document:{id}",
                "card": "urn:ecume:card:{id}",
            },
            "mapping_notes": {
                "mbse_uaf": "Prepared as a simple effect/object/action/condition/task graph. Formal UAF mapping is intentionally not asserted in the MVP.",
                "rdf_linked_data": "JSON-LD uses stable URNs and ECUME vocabulary terms without claiming a complete ontology.",
                "memgraph": "CSV files use node ids and directed source/target edges.",
            },
        },
        "documents": documents,
        "cards": enriched_cards,
        "nodes": enriched_nodes,
        "edges": enriched_edges,
        "changelog": changelog,
        "mappings": {
            "relation_descriptions": RELATION_DESCRIPTIONS,
            "node_types": {
                "effect": "Effet métier à atteindre ou maintenir.",
                "object": "Objet métier concerné.",
                "action": "Action exercée ou proposée.",
                "condition": "Condition d'application ou de déclenchement.",
                "task": "Tâche concrète à réaliser.",
                "theme": "Thème détecté dans une source.",
            },
        },
    }


def _enrich_node(
    node: dict, aliases: list[dict], doc_by_id: dict[str, dict], card_by_id: dict[str, dict]
) -> dict:
    source_ids = node.get("source_ids", [])
    metadata = node.get("metadata", {})
    card_id = metadata.get("card_id")
    origin_card = card_by_id.get(card_id) if card_id else None
    return {
        **node,
        "uri": f"urn:ecume:node:{node['id']}",
        "canonical_label": node["label"],
        "aliases": aliases,
        "source_titles": _source_titles(source_ids, doc_by_id),
        "origin_card_id": card_id,
        "origin_card": _card_summary(origin_card) if origin_card else None,
        "source_excerpt": metadata.get("source_excerpt", ""),
    }


def _enrich_edge(
    edge: dict, node_by_id: dict[str, dict], doc_by_id: dict[str, dict], card_by_id: dict[str, dict]
) -> dict:
    source = node_by_id.get(edge["source_node_id"], {})
    target = node_by_id.get(edge["target_node_id"], {})
    metadata = edge.get("metadata", {})
    card_id = metadata.get("card_id")
    origin_card = card_by_id.get(card_id) if card_id else None
    relation_type = edge["relation_type"]
    return {
        **edge,
        "uri": f"urn:ecume:edge:{edge['id']}",
        "source_label": source.get("label", ""),
        "target_label": target.get("label", ""),
        "description": metadata.get("reason") or RELATION_DESCRIPTIONS.get(relation_type, ""),
        "direction": f"{source.get('label', edge['source_node_id'])} --{relation_type}--> {target.get('label', edge['target_node_id'])}",
        "source_titles": _source_titles(edge.get("source_ids", []), doc_by_id),
        "origin_card_id": card_id,
        "origin_card": _card_summary(origin_card) if origin_card else None,
    }


def _enrich_card(card: dict, doc_by_id: dict[str, dict]) -> dict:
    return {
        **card,
        "uri": f"urn:ecume:card:{card['id']}",
        "source_document_title": doc_by_id.get(card["document_id"], {}).get("title", ""),
    }


def _source_titles(source_ids: list[str], doc_by_id: dict[str, dict]) -> list[str]:
    return [doc_by_id[source_id]["title"] for source_id in source_ids if source_id in doc_by_id]


def _card_summary(card: dict | None) -> dict | None:
    if not card:
        return None
    return {
        "id": card["id"],
        "theme_label": card["theme_label"],
        "main_effect": card["main_effect"],
        "status": card["status"],
        "source_excerpt": card["source_excerpt"],
    }


def _list_documents() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM source_documents ORDER BY created_at ASC").fetchall()
    documents = rows_to_dicts(rows)
    for doc in documents:
        content = doc.get("content_text", "")
        doc["uri"] = f"urn:ecume:document:{doc['id']}"
        doc["content_text_length"] = len(content)
        doc["content_preview"] = content[:1200]
    return documents


def _list_cards() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM extracted_cards ORDER BY created_at ASC").fetchall()
    return rows_to_dicts(rows)


def _list_nodes() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM knowledge_nodes ORDER BY created_at ASC").fetchall()
    return rows_to_dicts(rows)


def _list_edges() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM knowledge_edges ORDER BY created_at ASC").fetchall()
    return rows_to_dicts(rows)


def _list_changelog() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM change_log ORDER BY created_at ASC").fetchall()
    return rows_to_dicts(rows)


def _aliases_by_node() -> dict[str, list[dict]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_node_aliases ORDER BY created_at ASC"
        ).fetchall()
    aliases: dict[str, list[dict]] = {}
    for alias in rows_to_dicts(rows):
        aliases.setdefault(alias["node_id"], []).append(
            {
                "id": alias["id"],
                "label": alias["label"],
                "kind": alias["kind"],
                "created_at": alias["created_at"],
                "source_id": alias["source_id"],
            }
        )
    return aliases


def _write_nodes(path: Path, nodes: list[dict]) -> None:
    fields = [
        "id",
        "label",
        "canonical_label",
        "aliases",
        "type",
        "level",
        "description",
        "status",
        "confidence",
        "source_ids",
        "source_titles",
        "created_at",
        "updated_at",
        "uri",
        "origin_card_id",
        "source_excerpt",
        "metadata",
    ]
    _write_csv(path, fields, nodes)


def _write_edges(path: Path, edges: list[dict]) -> None:
    fields = [
        "id",
        "source_node_id",
        "source_label",
        "target_node_id",
        "target_label",
        "relation_type",
        "label",
        "description",
        "direction",
        "status",
        "confidence",
        "source_ids",
        "source_titles",
        "created_at",
        "updated_at",
        "uri",
        "origin_card_id",
        "metadata",
    ]
    _write_csv(path, fields, edges)


def _write_documents(path: Path, documents: list[dict]) -> None:
    fields = [
        "id",
        "title",
        "filename",
        "file_type",
        "content_text_length",
        "content_preview",
        "created_at",
        "uri",
        "metadata",
    ]
    _write_csv(path, fields, documents)


def _write_cards(path: Path, cards: list[dict]) -> None:
    fields = [
        "id",
        "document_id",
        "source_document_title",
        "theme_label",
        "main_effect",
        "level",
        "objects",
        "actions",
        "conditions",
        "tasks",
        "suggested_links",
        "confidence",
        "status",
        "source_excerpt",
        "created_at",
        "updated_at",
        "uri",
    ]
    _write_csv(path, fields, cards)


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fields})


def _csv_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return str(value)


def _memgraph_cypher() -> str:
    return """
// Run from the directory containing memgraph_nodes.csv and memgraph_edges.csv.
// Memgraph stores ECUME relation types as properties on ECUME_RELATION edges.

LOAD CSV FROM "memgraph_nodes.csv" WITH HEADER AS row
MERGE (n:EcumeNode {id: row.id})
SET n.label = row.label,
    n.canonical_label = row.canonical_label,
    n.aliases = row.aliases,
    n.type = row.type,
    n.level = row.level,
    n.description = row.description,
    n.status = row.status,
    n.confidence = row.confidence,
    n.source_ids = row.source_ids,
    n.source_titles = row.source_titles,
    n.created_at = row.created_at,
    n.updated_at = row.updated_at,
    n.uri = row.uri,
    n.origin_card_id = row.origin_card_id,
    n.source_excerpt = row.source_excerpt,
    n.metadata = row.metadata;

LOAD CSV FROM "memgraph_edges.csv" WITH HEADER AS row
MATCH (source:EcumeNode {id: row.source_node_id}), (target:EcumeNode {id: row.target_node_id})
CREATE (source)-[r:ECUME_RELATION {id: row.id}]->(target)
SET r.relation_type = row.relation_type,
    r.label = row.label,
    r.description = row.description,
    r.direction = row.direction,
    r.status = row.status,
    r.confidence = row.confidence,
    r.source_ids = row.source_ids,
    r.source_titles = row.source_titles,
    r.created_at = row.created_at,
    r.updated_at = row.updated_at,
    r.uri = row.uri,
    r.origin_card_id = row.origin_card_id,
    r.metadata = row.metadata;
""".strip()


def _ttl_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
