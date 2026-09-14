from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from test_mvp import isolated_data_dir
from test_documents import upload, create_card, knowledge_snapshot
from app.database import db
from app.main import app
from app.models.schemas import AliasRequest, CardUpdate, KnowledgeEdgeIn, KnowledgeNodeIn
from app.services import card_service as cards, document_service as docs, graph_service as graph
from app.services import validation_service as validation


def node(label, **kwargs):
    return graph.create_node(KnowledgeNodeIn(label=label, type=kwargs.pop("type", "effect"), **kwargs))


def test_target_search_is_bounded_stable_and_read_only():
    for index in range(19):
        node(f"Coordination secteur {index:02}")
    before = knowledge_snapshot()
    settings = validation.get_settings()
    first = graph.search_targets("coordination")
    second = graph.search_targets("coordination", offset=8)
    last = graph.search_targets("coordination", offset=16)
    assert first["total"] == second["total"] == last["total"] == 19
    assert [len(page["items"]) for page in (first, second, last)] == [8, 8, 3]
    assert first["has_more"] and second["has_more"] and not last["has_more"]
    assert len({item["id"] for page in (first, second, last) for item in page["items"]}) == 19
    assert graph.search_targets("coordination") == first
    assert knowledge_snapshot() == before
    assert validation.get_settings() == settings


def test_target_alias_and_accents_rank_before_partial_label():
    partial = node("Securite des interventions")
    exact = node("Protection")
    graph.add_alias(exact["id"], AliasRequest(label="Sécurité", kind="synonym"))
    result = graph.search_targets(" SECURITE ")["items"]
    assert [item["id"] for item in result[:2]] == [exact["id"], partial["id"]]


def test_target_search_filters_and_provenance_survive_source_purge():
    source = upload()
    own = node("Coordination source", source_ids=[source["id"]])
    good = node("Coordination validee", status="accepted", source_ids=[source["id"]],
                description="Suivi des equipes", business_category="action_activite")
    pending = node("Coordination a traiter")
    rejected = node("Coordination rejetee", status="rejected")
    linked = node("Coordination fusionnee", status="linked")
    other_type = node("Coordination objet", type="object")
    graph.create_edge(KnowledgeEdgeIn(source_node_id=own["id"], target_node_id=good["id"], relation_type="concerne"))
    result = graph.search_targets("coordination", source_id=own["id"], document_id=source["id"])
    ids = {item["id"] for item in result["items"]}
    assert ids == {good["id"], pending["id"], other_type["id"]}
    item = next(item for item in result["items"] if item["id"] == good["id"])
    assert item["already_linked"]
    assert item["source_titles"] == [source["title"]]
    assert item["description"] == "Suivi des equipes"
    assert item["business_category"] == "action_activite"
    assert graph.search_targets("coordination", scope="validated")["total"] == 1
    assert graph.search_targets("coordination", source_id=own["id"], scope="document", document_id=source["id"])["total"] == 1
    assert other_type["id"] not in {item["id"] for item in graph.search_targets("coordination", node_type="effect")["items"]}
    docs.purge_source(source["id"])
    assert graph.search_targets("coordination", scope="validated")["items"][0]["source_titles"] == [source["title"]]


def test_target_close_filter_excludes_description_only_matches():
    target = node("Coordination")
    node("Archive", description="Coordination")
    assert graph.search_targets("coordination")["total"] == 2
    assert [item["id"] for item in graph.search_targets("coordination", scope="close")["items"]] == [target["id"]]


@pytest.mark.parametrize("params", [
    {"q": "a"}, {"q": ""}, {"q": "  "},
])
def test_short_target_queries_do_not_dump_the_graph(params):
    node("Archive")
    with TestClient(app) as client:
        response = client.get("/graph/targets", params=params)
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "has_more": False}


@pytest.mark.parametrize("params", [
    {"limit": 9}, {"limit": 0}, {"offset": -1}, {"scope": "invalid"},
    {"node_type": "invalid"}, {"q": "x" * 201},
])
def test_target_api_rejects_invalid_search_parameters(params):
    with TestClient(app) as client:
        assert client.get("/graph/targets", params=params).status_code == 422


def test_document_card_counts_are_not_concept_counts():
    source = upload()
    accepted = create_card(source, "Resultat valide", ["Objet", "Autre objet"])
    review = create_card(source, "Resultat a revoir")
    rejected = create_card(source, "Resultat rejete")
    create_card(source, "Resultat en attente")
    cards.accept_card(accepted["id"])
    cards.update_card(review["id"], CardUpdate(status="to_confirm"))
    cards.update_card(rejected["id"], CardUpdate(status="rejected"))
    summary = docs.document_summary(source["id"])
    assert summary["card_count"] == 4
    assert summary["card_counts"] == {"validated": 1, "auto_validated": 0, "to_review": 1,
                                       "rejected": 1, "pending": 1, "linked": 0}
    assert summary["concept_counts"]["validated"] > summary["card_counts"]["validated"]
    assert docs.purge_source(source["id"])["card_counts"] == summary["card_counts"]


def test_document_counts_separate_auto_validated_and_merged_cards():
    source = upload()
    current = create_card(source)
    with db.get_db() as conn:
        conn.execute("UPDATE extracted_cards SET status = 'accepted', business_validation_status = 'auto_validated' WHERE id = ?", (current["id"],))
    assert docs.document_summary(source["id"])["card_counts"]["auto_validated"] == 1
    with db.get_db() as conn:
        conn.execute("UPDATE extracted_cards SET status = 'linked' WHERE id = ?", (current["id"],))
    assert docs.document_summary(source["id"])["card_counts"]["linked"] == 1
