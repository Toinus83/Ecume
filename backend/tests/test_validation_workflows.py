from __future__ import annotations

import csv
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from test_mvp import isolated_data_dir
from test_documents import upload, create_card
from app.database import db
from app.main import app
from app.models.schemas import AliasRequest, CardUpdate, KnowledgeEdgeIn, KnowledgeNodeIn, MainEffect, OrphanUpdate, ValidationSettings
from app.services import analysis_service as analysis, card_service as cards, coherence_service as coherence
from app.services import document_service as docs, export_service as exports, graph_service as graph, orphan_service as orphans, validation_service as validation


def analyzed(source, confidence=0.95, mode="assisted", **extra):
    raw = {"theme_label": "Theme", "main_effect": {"label": "Resultat", "description": "Definition explicite", "level": "tactical"},
           "business_category": "resultat_recherche", "business_confidence": confidence, **extra}
    return analysis._store_card(source, raw, [], validation_policy=ValidationSettings(mode=mode).model_dump())


@pytest.mark.parametrize("mode,score,expected", [
    ("strict", .99, "needs_user_validation"), ("assisted", .9, "auto_validated"),
    ("assisted", .899, "to_review"), ("assisted", .6, "to_review"),
    ("assisted", .599, "needs_user_validation"), ("automatic", .6, "auto_validated"),
    ("automatic", .599, "to_review"), ("automatic", None, "needs_user_validation"),
    ("assisted", "high", "needs_user_validation"), ("automatic", float("nan"), "needs_user_validation"),
])
def test_validation_thresholds(mode, score, expected):
    current = analyzed(upload(), score, mode)
    assert current["business_validation_status"] == expected
    assert current["archimate_mapping_status"] in {"candidate", "proposed_by_llm"}
    assert current["ontology_mapping_status"] == "to_map_later"
    validated = graph.graph_payload()["nodes"]
    assert bool(validated) == (expected == "auto_validated")
    if expected == "auto_validated":
        assert all(node["business_validation_status"] == "auto_validated" for node in validated)


def test_auto_validation_is_traced_in_all_exports_and_not_reapplied():
    source = upload()
    current = analyzed(source)
    coherence.refresh_states()
    payload = json.loads(exports.export_json().read_text(encoding="utf-8"))
    assert payload["cards"][0]["business_validation_status"] == "auto_validated"
    assert payload["nodes"][0]["validation_decision"]["policy"]["mode"] == "assisted"
    assert docs.document_summary(source["id"])["concept_counts"]["auto_validated"] == 2
    with zipfile.ZipFile(exports.export_csv_bundle()) as bundle:
        rows = list(csv.DictReader(io.StringIO(bundle.read("nodes.csv").decode("utf-8-sig"))))
        assert rows[0]["business_validation_status"] == "auto_validated"
        assert float(rows[0]["business_confidence"]) == .95
    cards.update_card(current["id"], CardUpdate(status="rejected"))
    validation.apply_to_new_card(current["id"], {"business_confidence": 1}, validation.get_settings(), [])
    assert analysis.get_card(current["id"])["status"] == "rejected"
    assert graph.graph_payload()["nodes"] == []


def test_shared_human_validation_is_not_relabelled_automatic():
    source = upload()
    auto = analyzed(source, objects=["Commun"])
    human = create_card(source, "Autre resultat", ["Commun"])
    cards.accept_card(human["id"])
    shared = auto["graph_node_ids"]["objects"][0]
    assert graph.get_node(shared)["business_validation_status"] == "validated_by_user"
    cards.update_card(auto["id"], CardUpdate(status="to_confirm"))
    assert graph.get_node(shared)["business_validation_status"] == "validated_by_user"


def test_ambiguous_or_unqualified_card_is_not_auto_validated():
    source = upload()
    assert analyzed(source, ambiguities=["Deux interpretations"])["business_validation_status"] == "to_review"
    raw = {"main_effect": {"label": "Incertain", "description": "Texte", "level": "unknown"}, "business_confidence": .99}
    current = analysis._store_card(source, raw, [], validation_policy=validation.get_settings())
    assert current["business_validation_status"] == "to_review"


def test_strong_link_is_decided_independently_and_persists():
    target = graph.create_node(KnowledgeNodeIn(label="Cible", type="effect", status="accepted"))
    current = analyzed(upload(), suggested_links=[{"source_label": "Resultat", "target_existing_node_id": target["id"],
        "relation_type": "contribue à", "confidence": "high", "business_confidence": .99}])
    suggestion = current["suggested_links"][0]
    assert suggestion["status"] == "accepted"
    assert suggestion["validation_decision"]["origin"] == "validation_policy"
    coherence.refresh_states()
    edge = next(item for item in graph.graph_payload()["edges"] if item["id"] == suggestion["edge_id"])
    assert edge["business_validation_status"] == "auto_validated"
    assert edge["business_confidence"] == .99


def test_weak_link_remains_candidate_even_with_auto_validated_card():
    target = graph.create_node(KnowledgeNodeIn(label="Cible", type="effect", status="accepted"))
    current = analyzed(upload(), suggested_links=[{"source_label": "Resultat", "target_existing_node_id": target["id"],
        "relation_type": "proche de", "business_confidence": .5}])
    assert current["business_validation_status"] == "auto_validated"
    assert current["suggested_links"][0]["status"] == "proposed"


def test_settings_validate_order_and_do_not_reclassify_existing_cards():
    current = analyzed(upload())
    with TestClient(app) as client:
        assert client.put("/validation/settings", json={"review_threshold": .99, "auto_threshold": .5}).status_code == 422
        assert client.put("/validation/settings", json={"mode": "strict"}).status_code == 200
    db.init_db()
    assert validation.get_settings()["mode"] == "strict"
    assert analysis.get_card(current["id"])["business_validation_status"] == "auto_validated"


def standalone(label, node_type="effect"):
    return graph.create_node(KnowledgeNodeIn(label=label, type=node_type, status="accepted"))


def test_orphan_attachment_is_idempotent_exported_and_deletable():
    source, target = standalone("Source"), standalone("Cible")
    request = OrphanUpdate(target_node_id=target["id"])
    first = orphans.update_orphan(source["id"], request)
    second = orphans.update_orphan(source["id"], request)
    assert first["edge"]["id"] == second["edge"]["id"]
    assert source["id"] not in {node["id"] for node in graph.find_orphans()}
    exported = json.loads(exports.export_json().read_text(encoding="utf-8"))
    assert exported["edges"][0]["id"] == first["edge"]["id"]
    graph.delete_edge(first["edge"]["id"])
    coherence.refresh_states()
    assert source["id"] in {node["id"] for node in graph.find_orphans()}


def test_decomposition_parent_direction_and_rejected_edges():
    parent, child = standalone("Parent"), standalone("Enfant")
    graph.create_edge(KnowledgeEdgeIn(source_node_id=parent["id"], target_node_id=child["id"], relation_type="se décompose en", status="accepted"))
    assert child["id"] not in {node["id"] for node in graph.find_orphans()}
    isolated = standalone("Objet", "object")
    graph.create_edge(KnowledgeEdgeIn(source_node_id=parent["id"], target_node_id=isolated["id"], relation_type="concerne", status="rejected"))
    assert isolated["id"] in {node["id"] for node in graph.find_orphans()}


def test_orphan_review_and_acceptance_share_graph_export_rules():
    source = upload()
    current = analyzed(source)
    node_id = current["graph_node_ids"]["effect"]
    orphans.update_orphan(node_id, OrphanUpdate(orphan_status="orphan_to_review"))
    coherence.refresh_states()
    assert node_id not in {node["id"] for node in graph.graph_payload()["nodes"]}
    assert json.loads(exports.export_json().read_text(encoding="utf-8"))["cards"] == []
    assert docs.document_summary(source["id"])["concept_counts"]["to_review"] > 0
    orphans.update_orphan(node_id, OrphanUpdate(orphan_status="accepted_orphan"))
    assert node_id in {node["id"] for node in graph.graph_payload()["nodes"]}


def test_orphan_correction_rolls_back_if_attachment_fails():
    current = create_card(upload())
    node_id = current["graph_node_ids"]["effect"]
    with pytest.raises(ValueError):
        orphans.update_orphan(node_id, OrphanUpdate(label="Modification", target_node_id="absent"))
    assert graph.get_node(node_id)["label"] == current["main_effect"]["label"]
    assert analysis.get_card(current["id"])["main_effect"] == current["main_effect"]


def test_shared_orphan_cannot_be_globally_renamed():
    first = create_card(upload(), objects=["Commun"])
    create_card(upload(), "Autre resultat", ["Commun"])
    with pytest.raises(ValueError, match="partage"):
        orphans.update_orphan(first["graph_node_ids"]["objects"][0], OrphanUpdate(label="Renomme"))


@pytest.mark.parametrize("status", ["rejected", "linked"])
def test_orphan_attachment_rejects_inactive_endpoints(status):
    source, target = standalone("Source"), standalone("Cible")
    with db.get_db() as conn:
        conn.execute("UPDATE knowledge_nodes SET status = ? WHERE id = ?", (status, target["id"]))
    with pytest.raises(ValueError, match="cible"):
        orphans.update_orphan(source["id"], OrphanUpdate(label="Renomme", target_node_id=target["id"]))
    assert graph.get_node(source["id"])["label"] == "Source"
    with pytest.raises(ValueError, match="carte source"):
        orphans.update_orphan(target["id"], OrphanUpdate(target_node_id=source["id"]))


def test_graph_search_uses_validated_nodes_aliases_and_direct_neighbors():
    source, target = standalone("Batiment"), standalone("Construction")
    graph.add_alias(source["id"], AliasRequest(label="Maison", kind="synonym"))
    orphans.update_orphan(source["id"], OrphanUpdate(target_node_id=target["id"], relation_type="concerne"))
    graph.create_node(KnowledgeNodeIn(label="Maison incertaine", type="effect", status="proposed"))
    results = graph.search_validated_graph("maison")
    assert len(results) == 1
    assert results[0]["node"]["id"] == source["id"]
    assert results[0]["neighbors"][0]["node"]["id"] == target["id"]
