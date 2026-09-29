from __future__ import annotations

from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import db
from app.main import app
from app.models.schemas import KnowledgeEdgeIn, KnowledgeNodeIn
from app.services import document_service, export_service, graph_service
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    export_dir = data_dir / "exports"
    monkeypatch.setattr(db, "DATA_DIR", data_dir)
    monkeypatch.setattr(db, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(db, "EXPORT_DIR", export_dir)
    monkeypatch.setattr(db, "DB_PATH", data_dir / "ecume.db")
    monkeypatch.setattr(document_service, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(export_service, "EXPORT_DIR", export_dir)
    db.init_db()


def test_create_document_from_upload():
    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            files={"file": ("procedure.txt", b"Verifier la disponibilite du service.", "text/plain")},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "procedure.txt"
    assert "content_text" not in payload
    assert "disponibilite" in document_service.get_document(payload["id"])["content_text"]
    assert payload["can_reanalyze"] is True


def test_create_node_and_edge():
    first = graph_service.create_node(KnowledgeNodeIn(label="Assurer le suivi", type="effect"))
    second = graph_service.create_node(KnowledgeNodeIn(label="Compte rendu", type="object"))
    edge = graph_service.create_edge(
        KnowledgeEdgeIn(
            source_node_id=first["id"],
            target_node_id=second["id"],
            relation_type="concerne",
        )
    )
    assert first["label"] == "Assurer le suivi"
    assert edge["relation_type"] == "concerne"


def test_orphan_detection():
    node = graph_service.create_node(KnowledgeNodeIn(label="Réduire le délai de traitement", type="effect"))
    orphans = graph_service.find_orphans()
    assert any(item["id"] == node["id"] for item in orphans)


def test_export_json_and_memgraph_csv():
    first = graph_service.create_node(KnowledgeNodeIn(label="Coordonner les équipes", type="effect"))
    second = graph_service.create_node(KnowledgeNodeIn(label="Planning", type="object"))
    graph_service.create_edge(
        KnowledgeEdgeIn(source_node_id=first["id"], target_node_id=second["id"], relation_type="concerne")
    )
    json_path = export_service.export_json()
    memgraph_path = export_service.export_memgraph_bundle()
    assert json_path.exists()
    assert json_path.name == "ecume_knowledge.json"
    assert memgraph_path.exists()
    with zipfile.ZipFile(memgraph_path) as bundle:
        names = set(bundle.namelist())
    assert {"memgraph_nodes.csv", "memgraph_edges.csv", "memgraph_import.cypher"} <= names
    with TestClient(app) as client:
        response = client.get("/export/json")
    assert response.status_code == 200
    assert "ecume_knowledge.json" in response.headers["content-disposition"]


def test_turtle_export_is_parseable_and_keeps_directed_relations():
    from rdflib import Graph, URIRef
    first = graph_service.create_node(KnowledgeNodeIn(label="Produire un bulletin", type="action", status="accepted", business_validation_status="validated_by_user"))
    second = graph_service.create_node(KnowledgeNodeIn(label="Bulletin meteo", type="object", status="accepted", business_validation_status="validated_by_user"))
    edge = graph_service.create_edge(
        KnowledgeEdgeIn(source_node_id=first["id"], target_node_id=second["id"], relation_type="concerne", status="accepted")
    )
    path = export_service.export_turtle()
    graph = Graph().parse(path, format="turtle")
    edge_uri = URIRef(f"urn:ecume:edge:{edge['id']}")
    assert path.name == "ecume_export.ttl"
    assert (edge_uri, URIRef("urn:ecume:vocab:source"), URIRef(f"urn:ecume:node:{first['id']}")) in graph
    assert (edge_uri, URIRef("urn:ecume:vocab:target"), URIRef(f"urn:ecume:node:{second['id']}")) in graph
    with TestClient(app) as client:
        response = client.get("/export/ttl")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/turtle")
