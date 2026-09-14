from __future__ import annotations

import csv
import io
import json
import zipfile

import pytest

from test_mvp import isolated_data_dir
from app.database import db
from app.models.schemas import CardUpdate, KnowledgeNodeIn, MainEffect, ManualCardRequest
from app.services import analysis_service as analysis, card_service as cards
from app.services import coherence_service as coherence, export_service as exports, graph_service as graph


def card(label="Traiter la demande", objects=None):
    return analysis.create_manual_card(ManualCardRequest(
        theme_label="Procedure", main_effect=MainEffect(label=label, description="Description initiale"),
        objects=objects or [],
    ))


def payload():
    return json.loads(exports.export_json().read_text(encoding="utf-8"))


def suggest(current, target, source_label=None):
    cards.update_card(current["id"], CardUpdate(suggested_links=[{
        "source_label": source_label or current["main_effect"]["label"],
        "target_existing_node_id": target["id"], "target_label": target["label"],
        "relation_type": "proche de", "reason": "A comparer",
    }]))
    return next(item for item in analysis.get_card(current["id"])["suggested_links"] if item["target_existing_node_id"] == target["id"])


def test_correction_reaches_graph_and_exports():
    current = card(objects=["Requerant"])
    cards.accept_card(current["id"])
    corrected = cards.update_card(current["id"], CardUpdate(
        main_effect=MainEffect(label="Qualifier la demande", description="Description corrigee", level="tactical"),
        level="tactical", objects=["Dossier"], actions=["Verifier"], conditions=["Dossier complet"], tasks=["Signer"],
    ))
    assert corrected["status"] == "to_confirm"
    cards.accept_card(current["id"])
    result = payload()
    effect = next(node for node in result["nodes"] if node["id"] == corrected["graph_node_ids"]["effect"])
    assert (effect["label"], effect["description"], effect["level"]) == ("Qualifier la demande", "Description corrigee", "tactical")
    assert {"Dossier", "Verifier", "Dossier complet", "Signer"} <= {n["label"] for n in result["nodes"]}
    assert "Requerant" not in {n["label"] for n in result["nodes"]}
    ids = {node["id"] for node in result["nodes"]}
    assert all(edge["source_node_id"] in ids and edge["target_node_id"] in ids for edge in result["edges"])


@pytest.mark.parametrize("action", ["reject", "delete", "detach"])
def test_shared_concept_survives_local_actions(action):
    first = card(objects=["Requerant"])
    second = card("Archiver la facture", ["Requerant"])
    shared = first["graph_node_ids"]["objects"][0]
    assert second["graph_node_ids"]["objects"] == [shared]
    cards.accept_card(first["id"])
    cards.accept_card(second["id"])
    if action == "reject":
        cards.update_card(first["id"], CardUpdate(status="rejected"))
    elif action == "delete":
        cards.delete_card(first["id"])
    else:
        cards.detach_concept(first["id"], shared)
    assert graph.get_node(shared)["status"] == "accepted"
    assert shared in {node["id"] for node in payload()["nodes"]}
    assert first["id"] not in {c["id"] for c in payload()["cards"]}
    with pytest.raises(ValueError, match="utilise"):
        graph.delete_node(shared)


def test_shared_effect_correction_creates_local_variant():
    first, second = card(), card()
    original = first["graph_node_ids"]["effect"]
    assert second["graph_node_ids"]["effect"] == original
    cards.accept_card(first["id"])
    cards.accept_card(second["id"])
    changed = cards.update_card(first["id"], CardUpdate(main_effect=MainEffect(label="Nouvelle interpretation", description="Locale")))
    assert changed["graph_node_ids"]["effect"] != original
    assert graph.get_node(original)["label"] == second["main_effect"]["label"]
    assert graph.get_node(original)["status"] == "accepted"


def test_suggestion_acceptance_is_persistent_and_idempotent():
    current = card(objects=["Requerant"])
    cards.accept_card(current["id"])
    target = graph.create_node(KnowledgeNodeIn(label="Destinataire", type="object", status="accepted"))
    item = suggest(current, target, "Requerant")
    assert not [edge for edge in payload()["edges"] if edge["target_node_id"] == target["id"]]
    first = coherence.decide_suggestion(current["id"], item["id"], "accepted")
    second = coherence.decide_suggestion(current["id"], item["id"], "accepted")
    assert first["edge_id"] == second["edge_id"]
    assert analysis.get_card(current["id"])["suggested_links"][0]["status"] == "accepted"
    edges = [edge for edge in payload()["edges"] if edge["id"] == first["edge_id"]]
    assert len(edges) == 1
    assert edges[0]["source_node_id"] == current["graph_node_ids"]["objects"][0]


@pytest.mark.parametrize("decision", ["ignored", "rejected", "to_review"])
def test_nonaccepted_suggestion_is_not_exported(decision):
    current = card()
    cards.accept_card(current["id"])
    target = graph.create_node(KnowledgeNodeIn(label="Autre resultat", type="effect", status="accepted"))
    item = suggest(current, target)
    accepted = coherence.decide_suggestion(current["id"], item["id"], "accepted")
    coherence.decide_suggestion(current["id"], item["id"], decision)
    suggest(current, target)
    assert analysis.get_card(current["id"])["suggested_links"][0]["status"] == decision
    assert accepted["edge_id"] not in {edge["id"] for edge in payload()["edges"]}
    assert accepted["edge_id"] not in {edge["id"] for edge in graph.graph_payload()["edges"]}


def test_category_change_recalculates_mapping_and_requires_validation():
    current = card()
    cards.accept_card(current["id"])
    updated = cards.update_card(current["id"], CardUpdate(business_category="capacite_a_obtenir"))
    assert updated["archimate_mapping"]["candidate_element"] == "Capability"
    assert updated["archimate_mapping_status"] == "inferred_from_user_answer"
    assert updated["business_validation_status"] == "corrected_by_user"
    assert updated["ontology_mapping_status"] == "to_map_later"
    assert not payload()["cards"]
    cards.accept_card(current["id"])
    node = next(node for node in payload()["nodes"] if node["type"] == "effect")
    assert node["archimate_mapping"]["candidate_element"] == "Capability"


@pytest.mark.parametrize("status", ["rejected", "to_confirm"])
def test_archimate_excludes_rejected_and_review(status):
    current = card()
    cards.accept_card(current["id"])
    cards.update_card(current["id"], CardUpdate(status=status))
    exported = json.loads(exports.export_archimate_candidates_json().read_text(encoding="utf-8"))
    assert not exported["candidates"]


def test_memgraph_preserves_ids_and_uses_merge():
    current = card(objects=["Requerant"])
    cards.accept_card(current["id"])
    def read():
        with zipfile.ZipFile(exports.export_memgraph_bundle()) as bundle:
            rows = list(csv.DictReader(io.StringIO(bundle.read("memgraph_edges.csv").decode("utf-8-sig"))))
            script = bundle.read("memgraph_import.cypher").decode()
        return rows, script
    first, script = read()
    second, _ = read()
    assert first and [row["id"] for row in first] == [row["id"] for row in second]
    assert "MERGE (source)-[r:ECUME_RELATION {id: row.id}]->(target)" in script
    assert len({(row["source_node_id"], row["target_node_id"], row["relation_type"]) for row in first}) == len(first)


def test_action_rolls_back_card_graph_and_history(monkeypatch):
    current = card()
    before = exports._complete_export_payload("all")
    def fail(**kwargs):
        raise RuntimeError("audit failure")
    monkeypatch.setattr(cards, "record_change", fail)
    with pytest.raises(RuntimeError):
        cards.update_card(current["id"], CardUpdate(main_effect=MainEffect(label="Correction annulee")))
    after = exports._complete_export_payload("all")
    for field in ("cards", "nodes", "edges", "changelog"):
        assert before[field] == after[field]


def test_migration_is_repeatable_and_preserves_decisions():
    current = card()
    target = graph.create_node(KnowledgeNodeIn(label="Cible", type="effect"))
    item = suggest(current, target)
    coherence.decide_suggestion(current["id"], item["id"], "ignored")
    db.init_db()
    db.init_db()
    assert analysis.get_card(current["id"])["suggested_links"][0]["status"] == "ignored"


def test_jsonld_contains_sources_cards_history_and_mapping_context():
    current = card()
    cards.accept_card(current["id"])
    exported = json.loads(exports.export_jsonld().read_text(encoding="utf-8"))
    assert exported["@context"]["@vocab"] == "urn:ecume:vocab:"
    assert any(item["@id"] == f"urn:ecume:card:{current['id']}" for item in exported["@graph"])
    assert any(item["@type"] == "ecume:change" for item in exported["@graph"])


def test_near_match_remains_a_proposal_not_an_automatic_merge():
    first = graph.create_node(KnowledgeNodeIn(label="Requerant principal", type="object"))
    second = graph.create_node(KnowledgeNodeIn(label="Requerant secondaire", type="object"))
    assert first["id"] != second["id"]


def legacy_database():
    with db.get_db() as conn:
        for table in ("card_concepts", "card_relations", "link_suggestions", "coherence_migrations"):
            conn.execute(f"DELETE FROM {table}")


def test_legacy_shared_bindings_are_recovered_without_data_loss():
    first, second = card(objects=["Requerant"]), card(objects=["Requerant"])
    cards.accept_card(first["id"])
    cards.accept_card(second["id"])
    before_ids = {node["id"] for node in graph.list_nodes()}
    legacy_database()
    db.init_db()
    db.init_db()
    assert {node["id"] for node in graph.list_nodes()} == before_ids
    assert set(coherence.concept_users(first["graph_node_ids"]["effect"])) == {first["id"], second["id"]}
    cards.delete_card(first["id"])
    assert len(payload()["cards"]) == 1
    assert payload()["edges"]
    assert all(edge["status"] == "accepted" for edge in payload()["edges"])


@pytest.mark.parametrize("damage", ["label", "missing_node", "list_length"])
def test_legacy_inconsistencies_are_reviewed_then_repairable(damage):
    current = card(objects=["Requerant"])
    cards.accept_card(current["id"])
    legacy_database()
    with db.get_db() as conn:
        if damage == "label":
            effect = {**current["main_effect"], "label": "Correction ancienne"}
            conn.execute("UPDATE extracted_cards SET main_effect = ? WHERE id = ?", (json.dumps(effect), current["id"]))
        elif damage == "missing_node":
            conn.execute("DELETE FROM knowledge_nodes WHERE id = ?", (current["graph_node_ids"]["objects"][0],))
        else:
            conn.execute("UPDATE extracted_cards SET objects = ? WHERE id = ?", (json.dumps(["Requerant", "Document ajoute"]), current["id"]))
    db.init_db()
    recovered = analysis.get_card(current["id"])
    assert recovered["business_validation_status"] == "to_review"
    assert not payload()["cards"]
    repaired = cards.accept_card(current["id"])
    assert cards._content_matches(repaired)
    assert payload()["cards"][0]["id"] == current["id"]


def test_legacy_automatic_suggestion_is_not_certified_by_card_validation():
    current = card()
    target = graph.create_node(KnowledgeNodeIn(label="Reference", type="effect", status="accepted"))
    suggest(current, target)
    from app.models.schemas import KnowledgeEdgeIn
    edge = graph.create_edge(KnowledgeEdgeIn(source_node_id=current["graph_node_ids"]["effect"],
        target_node_id=target["id"], relation_type="proche de", status="accepted", metadata={"card_id": current["id"], "origin": "import"}))
    cards.accept_card(current["id"])
    legacy_database()
    db.init_db()
    item = analysis.get_card(current["id"])["suggested_links"][0]
    assert item["status"] == "to_review"
    assert edge["id"] not in {e["id"] for e in payload()["edges"]}
    coherence.decide_suggestion(current["id"], item["id"], "accepted")
    assert edge["id"] in {e["id"] for e in payload()["edges"]}
    coherence.decide_suggestion(current["id"], item["id"], "ignored")
    assert edge["id"] not in {e["id"] for e in payload()["edges"]}


def test_upgrade_of_in_progress_migration_preserves_decisions():
    current = card()
    target = graph.create_node(KnowledgeNodeIn(label="Reference", type="effect"))
    item = suggest(current, target)
    coherence.decide_suggestion(current["id"], item["id"], "ignored")
    with db.get_db() as conn:
        conn.execute("DELETE FROM coherence_migrations WHERE name = 'bindings_v2'")
    db.init_db()
    assert analysis.get_card(current["id"])["suggested_links"][0]["status"] == "ignored"


def test_card_merge_preserves_shared_concepts_sources_and_ignored_decisions():
    source = card("Verifier la demande", ["Requerant", "Dossier"])
    target = card("Archiver la facture", ["Facture"])
    third = card("Contacter le client", ["Requerant"])
    for current in (source, target, third):
        cards.accept_card(current["id"])
    reference = graph.create_node(KnowledgeNodeIn(label="Reference", type="effect", status="accepted"))
    item = suggest(source, reference)
    coherence.decide_suggestion(source["id"], item["id"], "ignored")
    merged = cards.merge_card(source["id"], target["id"])
    assert merged["objects"] == ["Facture", "Requerant", "Dossier"]
    assert merged["status"] == "to_confirm"
    assert analysis.get_card(source["id"])["status"] == "linked"
    assert any(item["status"] == "ignored" for item in merged["suggested_links"])
    cards.accept_card(target["id"])
    exported = payload()
    assert source["id"] not in {item["id"] for item in exported["cards"]}
    assert graph.get_node(source["graph_node_ids"]["objects"][0])["status"] == "accepted"
    dossier = next(node for node in exported["nodes"] if node["label"] == "Dossier")
    assert {source["document_id"], target["document_id"]} <= set(dossier["source_ids"])
    assert any(change["action"] == "merged" for change in exported["changelog"])


def test_card_merge_is_atomic(monkeypatch):
    first, second = card("Verifier la demande", ["Requerant"]), card("Archiver la facture", ["Facture"])
    before = exports._complete_export_payload("all")
    original = cards.record_change
    def fail_merge(**kwargs):
        if kwargs["action"] == "merged":
            raise RuntimeError("merge failure")
        return original(**kwargs)
    monkeypatch.setattr(cards, "record_change", fail_merge)
    with pytest.raises(RuntimeError):
        cards.merge_card(first["id"], second["id"])
    after = exports._complete_export_payload("all")
    for field in ("cards", "nodes", "edges", "changelog"):
        assert before[field] == after[field]


def test_global_merge_protects_card_concepts():
    current = card(objects=["Requerant"])
    target = graph.create_node(KnowledgeNodeIn(label="Client", type="object"))
    with pytest.raises(ValueError, match="bloquee"):
        graph.merge_nodes(current["graph_node_ids"]["objects"][0], target["id"])


def test_unbound_node_merge_preserves_aliases_and_deduplicates_edges():
    from app.models.schemas import AliasRequest, KnowledgeEdgeIn
    first = graph.create_node(KnowledgeNodeIn(label="Requerant", type="object", status="accepted", source_ids=["doc-a"]))
    second = graph.create_node(KnowledgeNodeIn(label="Client", type="object", status="accepted", source_ids=["doc-b"]))
    parent = graph.create_node(KnowledgeNodeIn(label="Service", type="effect", status="accepted"))
    graph.add_alias(first["id"], AliasRequest(label="Demandeur", kind="synonym"))
    for node in (first, second):
        graph.create_edge(KnowledgeEdgeIn(source_node_id=parent["id"], target_node_id=node["id"], relation_type="concerne", status="accepted"))
    graph.merge_nodes(first["id"], second["id"])
    result = payload()
    assert len(result["edges"]) == 1
    target = next(node for node in result["nodes"] if node["id"] == second["id"])
    assert {"Requerant", "Demandeur"} <= {alias["label"] for alias in target["aliases"]}
    assert set(target["source_ids"]) == {"doc-a", "doc-b"}


def test_shared_effect_mapping_is_not_downgraded_by_other_card():
    first, second = card(), card()
    cards.update_card(first["id"], CardUpdate(status="to_confirm"))
    cards.accept_card(second["id"])
    node = graph.get_node(second["graph_node_ids"]["effect"])
    assert node["archimate_mapping_status"] == "candidate"
    cards.update_card(first["id"], CardUpdate(status="rejected"))
    assert graph.get_node(node["id"])["archimate_mapping_status"] == "candidate"


def test_deleted_structural_relation_does_not_reappear_after_correction():
    current = card(objects=["Requerant"])
    cards.accept_card(current["id"])
    edge = next(e for e in payload()["edges"] if e["target_node_id"] == current["graph_node_ids"]["objects"][0])
    graph.delete_edge(edge["id"])
    cards.update_card(current["id"], CardUpdate(level="tactical"))
    cards.accept_card(current["id"])
    assert edge["id"] not in {e["id"] for e in payload()["edges"]}


def test_concept_used_as_suggestion_target_survives_original_card_deletion():
    original = card("Traiter la demande", ["Requerant"])
    other = card("Archiver la facture", ["Facture"])
    for current in (original, other):
        cards.accept_card(current["id"])
    target_id = original["graph_node_ids"]["objects"][0]
    item = suggest(other, graph.get_node(target_id), "Facture")
    coherence.decide_suggestion(other["id"], item["id"], "accepted")
    cards.delete_card(original["id"])
    assert target_id in {n["id"] for n in payload()["nodes"]}
    with pytest.raises(ValueError):
        graph.delete_node(target_id)
    cards.delete_card(other["id"])
    assert target_id not in {n["id"] for n in payload()["nodes"]}


def test_shared_suggestion_edge_keeps_other_cards_acceptance():
    first, second = card(objects=["Requerant"]), card("Archiver la facture", ["Requerant"])
    reference = graph.create_node(KnowledgeNodeIn(label="Destinataire", type="object", status="accepted"))
    decisions = []
    for current in (first, second):
        cards.accept_card(current["id"])
        item = suggest(current, reference, "Requerant")
        decisions.append(coherence.decide_suggestion(current["id"], item["id"], "accepted"))
    assert decisions[0]["edge_id"] == decisions[1]["edge_id"]
    coherence.decide_suggestion(first["id"], decisions[0]["id"], "ignored")
    assert decisions[1]["edge_id"] in {e["id"] for e in payload()["edges"]}


@pytest.mark.parametrize("mode", ["all", "effects", "effects_objects", "effects_actions", "orphans"])
def test_graph_filters_never_return_dangling_edges(mode):
    current = card(objects=["Requerant"])
    cards.accept_card(current["id"])
    result = graph.graph_payload(filter_mode=mode)
    ids = {node["id"] for node in result["nodes"]}
    assert all(e["source_node_id"] in ids and e["target_node_id"] in ids for e in result["edges"])


def test_decision_api_and_global_delete_guard():
    from fastapi.testclient import TestClient
    from app.main import app
    current = card(objects=["Requerant"])
    target = graph.create_node(KnowledgeNodeIn(label="Destinataire", type="object", status="accepted"))
    item = suggest(current, target, "Requerant")
    with TestClient(app) as client:
        assert client.post(f"/cards/{current['id']}/accept").status_code == 200
        response = client.post(f"/cards/{current['id']}/suggestions/{item['id']}/decision", json={"status": "accepted"})
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        node_id = current["graph_node_ids"]["objects"][0]
        assert client.delete(f"/graph/nodes/{node_id}").status_code != 200
        assert client.delete(f"/cards/{current['id']}/concepts/{node_id}").status_code == 200
        exported = client.get("/export/json")
        assert exported.status_code == 200
        assert exported.json()["export_metadata"]["scope"] == "validated"
