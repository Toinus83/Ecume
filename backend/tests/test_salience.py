from __future__ import annotations

import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient
from test_mvp import isolated_data_dir
from test_documents import upload, create_card, knowledge_snapshot
from app.database import db
from app.main import app
from app.models.schemas import CardUpdate, ValidationSettings
from app.llm.prompt import build_analysis_prompt
from app.services import analysis_service as analysis, card_service as cards, coherence_service as coherence
from app.services import document_service as docs, export_service as exports, graph_service as graph
from app.services import job_service as jobs, salience_service as salience, validation_service as validation


def proposal(label, role="objects", importance="principal", salience_score=.95, confidence=.95):
    return {"label": label, "role": role, "importance": importance, "salience_score": salience_score,
            "confidence": confidence, "reason": "Indispensable pour comprendre cette regle.", "source_excerpt": "Acces de 4 m sauf exception."}


def raw(concepts=None, label="Accessibilite des constructions"):
    return {"theme_label": "Reglement", "main_effect": {"label": label,
            "description": "Voie de 4 m et recul de 6 m, sauf extension existante.", "level": "tactical"},
            "business_category": "condition_regle_contrainte", "business_confidence": .97,
            "source_excerpt": "Voie de 4 m et recul de 6 m, sauf extension existante.",
            "rule_details": ["Distance minimale : 6 m. Exception : extension existante."],
            "concepts": concepts if concepts is not None else [proposal("Voie d'acces"), proposal("Batiment", importance="secondary"), proposal("Chose", importance="weak")]}


def store(source=None, mode="sober", payload=None, policy=None):
    return analysis._store_card(source or upload(), payload or raw(), [], extraction_mode=mode, validation_policy=policy)


@pytest.mark.parametrize("mode,limit", [("sober",4),("balanced",8),("exhaustive",14)])
def test_modes_select_a_small_graph_not_a_large_hidden_graph(mode, limit):
    proposals = [proposal(f"Concept {role} {i}", role=role) for role in salience.ROLES for i in range(10)]
    current = store(mode=mode, payload=raw(proposals))
    assert sum(len(current[role]) for role in salience.ROLES) == limit
    assert len(graph.list_nodes()) == limit + 1
    assert all(len(current[role]) <= salience.ROLE_LIMITS[role] for role in salience.ROLES)
    assert len(current["extraction_details"]["concepts"]) == 40
    assert sum(item["active"] for item in current["extraction_details"]["concepts"]) == limit
    assert current["graph_node_ids"]["theme"] == ""
    cards.accept_card(current["id"])
    assert len(graph.graph_payload()["nodes"]) == limit + 1
    assert "6 m" in current["main_effect"]["description"]
    assert "Exception" in current["extraction_details"]["rule_details"][0]


def test_legacy_cards_are_unchanged_by_additive_idempotent_migration():
    current = create_card(upload(), objects=[f"Objet {i}" for i in range(40)])
    cards.accept_card(current["id"])
    validation.save_settings(ValidationSettings(mode="automatic", auto_threshold=1, review_threshold=.28))
    before = knowledge_snapshot()
    db.init_db()
    db.init_db()
    assert knowledge_snapshot() == before
    assert analysis.get_card(current["id"])["extraction_details"] == {}
    assert validation.get_settings()["review_threshold"] == .28


@pytest.mark.parametrize("score", [None, "high", True, -1, 1.1, float("nan"), float("inf")])
def test_no_invented_salience_or_automatic_promotion(score):
    current = store(payload=raw([proposal("Contexte", salience_score=score)]))
    assert current["objects"] == []
    assert current["extraction_details"]["concepts"][0]["salience_score"] is None
    assert len(graph.list_nodes()) == 1


def test_missing_structured_concepts_stay_in_details():
    current = store(payload={**raw([]), "objects": ["Batiment", "Chose", "Condition"]})
    assert current["objects"] == []
    assert len(current["extraction_details"]["concepts"]) == 3
    assert len(graph.find_orphans()) == 1


def test_contextual_importance_preserves_shared_validated_concept():
    source = upload()
    principal = store(source, payload=raw([proposal("Batiment")]))
    cards.accept_card(principal["id"])
    secondary = store(source, payload=raw([proposal("Batiment", importance="secondary")], label="Implantation"))
    cards.accept_card(secondary["id"])
    shared_id = principal["graph_node_ids"]["objects"][0]
    assert graph.get_node(shared_id)["status"] == "accepted"
    assert secondary["objects"] == []
    assert salience.node_importance()[shared_id] == "principal"
    assert graph.search_targets("batiment")["items"][0]["id"] == shared_id
    assert secondary["extraction_details"]["concepts"][0]["importance"] == "secondary"


def test_secondary_requires_explicit_retention_and_card_revalidation():
    current = store()
    cards.accept_card(current["id"])
    candidate = next(item for item in current["extraction_details"]["concepts"] if item["label"] == "Batiment")
    assert all(node["label"] != "Batiment" for node in graph.list_nodes())
    retained = salience.decide_concept(current["id"], candidate["id"], "retain")
    assert retained["status"] == "to_confirm"
    saved = next(item for item in retained["extraction_details"]["concepts"] if item["id"] == candidate["id"])
    assert saved["active"] and saved["retained"] and saved["node_id"]
    assert saved["importance"] == "secondary"
    assert not graph.graph_payload()["nodes"]
    cards.accept_card(current["id"])
    assert any(node["label"] == "Batiment" for node in graph.graph_payload()["nodes"])
    with pytest.raises(ValueError, match="deja retenu"):
        salience.decide_concept(current["id"], candidate["id"], "retain")


def test_ignored_proposal_never_creates_a_node_and_is_traced():
    current = store()
    weak = next(item for item in current["extraction_details"]["concepts"] if item["importance"] == "weak")
    before = graph.list_nodes()
    result = salience.decide_concept(current["id"], weak["id"], "ignore")
    assert graph.list_nodes() == before
    assert next(item for item in result["extraction_details"]["concepts"] if item["id"] == weak["id"])["origin"] == "user"
    with db.get_db() as conn:
        assert conn.execute("SELECT 1 FROM change_log WHERE entity_id = ? AND action = 'concept_ignore'", (current["id"],)).fetchone()


def test_retention_rolls_back_on_graph_failure(monkeypatch):
    current = store()
    candidate = current["extraction_details"]["concepts"][1]
    before = knowledge_snapshot()
    def fail(*args, **kwargs):
        raise RuntimeError("simulated graph failure")
    monkeypatch.setattr(cards, "_synchronize_graph", fail)
    with pytest.raises(RuntimeError):
        salience.decide_concept(current["id"], candidate["id"], "retain")
    assert knowledge_snapshot() == before


def test_chunk_consolidation_keeps_rules_exceptions_and_sources():
    first = raw([proposal("Acces")])
    second = raw([proposal("Recul")])
    second["main_effect"]["description"] = "Hauteur maximale : 6,50 m ; sauf extension."
    second["source_excerpt"] = "Exception explicite pour les extensions."
    second["rule_details"] = ["Hauteur maximale : 6,50 m."]
    merged = analysis._consolidate_cards([first, second])
    assert len(merged) == 1
    current = store(payload=merged[0])
    assert "4 m" in current["main_effect"]["description"] and "6,50 m" in current["main_effect"]["description"]
    assert len(current["extraction_details"]["source_excerpts"]) == 2
    assert len(current["extraction_details"]["rule_details"]) == 2


def test_merge_keeps_deferred_evidence_and_human_ignore():
    source = store(payload=raw([proposal("Batiment")], label="Autre regle"))
    target = store(payload=raw([proposal("Batiment", importance="secondary")]))
    proposal_id = target["extraction_details"]["concepts"][0]["id"]
    salience.decide_concept(target["id"], proposal_id, "ignore")
    result = cards.merge_card(source["id"], target["id"])
    assert "Batiment" not in result["objects"]
    assert result["extraction_details"]["rule_details"]
    assert result["extraction_details"]["concepts"][0]["importance"] == "ignored"


def test_purge_and_json_archive_preserve_rule_evidence():
    source = upload()
    current = store(source)
    before = current["extraction_details"]
    docs.purge_source(source["id"])
    assert analysis.get_card(current["id"])["extraction_details"] == before
    archive = json.loads(exports.export_json(scope="all").read_text(encoding="utf-8"))
    assert archive["cards"][0]["extraction_details"] == before
    assert all(node["label"] != "Chose" for node in archive["nodes"])


def test_extraction_mode_is_frozen_in_job_and_passed_to_analysis(monkeypatch):
    received = []
    async def fake(document_id, progress_callback, *, validation_policy, extraction_mode):
        received.append(extraction_mode)
        return {"cards": [], "warnings": []}
    monkeypatch.setattr(analysis, "analyze_document", fake)
    source = upload()
    async def run():
        first = jobs.start_analysis_job(source["id"], extraction_mode="balanced")
        duplicate = jobs.start_analysis_job(source["id"], extraction_mode="exhaustive")
        assert duplicate["id"] == first["id"]
        await asyncio.gather(*list(jobs._tasks))
        assert jobs.get_job(first["id"])["metadata"]["extraction_mode"] == "balanced"
    asyncio.run(run())
    assert received == ["balanced"]
    with TestClient(app) as client:
        assert client.post(f"/documents/{source['id']}/analyze?extraction_mode=invalid").status_code == 422


def test_weak_or_broken_links_do_not_block_new_primary_card():
    payload = raw()
    payload["suggested_links"] = [{"source_label": "Chose", "target_existing_node_id": "missing", "relation_type": "concerne", "business_confidence": .95}]
    current = store(payload=payload, policy=ValidationSettings().model_dump())
    assert current["business_validation_status"] == "auto_validated"
    assert current["suggested_links"][0]["status"] == "proposed"
    assert not current["suggested_links"][0]["can_accept"]


def test_low_understanding_confidence_prevents_auto_validation_even_if_salient():
    current = store(payload=raw([proposal("Acces", confidence=.2)]), policy=ValidationSettings().model_dump())
    assert current["business_validation_status"] != "auto_validated"


@pytest.mark.parametrize("confidence", [None, .35])
def test_consolidation_does_not_hide_chunk_uncertainty(confidence):
    second = raw()
    second.update(business_confidence=confidence, ambiguities=["Exception a verifier"])
    merged = analysis._consolidate_cards([raw(), second])[0]
    assert merged["business_confidence"] == confidence
    current = store(payload=merged, policy=ValidationSettings().model_dump())
    assert current["business_validation_status"] != "auto_validated"
    assert "Exception a verifier" in current["extraction_details"]["ambiguities"]


def test_manual_correction_retains_previously_weak_concept_explicitly():
    current = store()
    result = cards.update_card(current["id"], CardUpdate(objects=[*current["objects"], "Chose"]))
    item = next(item for item in result["extraction_details"]["concepts"] if item["label"] == "Chose")
    assert item["active"] and item["retained"] and item["origin"] == "user"
    assert item["importance"] == "secondary"


def test_merge_same_content_rebuilds_local_bindings_on_legacy_target():
    source_doc = upload()
    target = create_card(source_doc, objects=["Batiment"])
    source = store(source_doc, payload=raw([proposal("Batiment")], label="Autre regle"))
    result = cards.merge_card(source["id"], target["id"])
    item = next(item for item in result["extraction_details"]["concepts"] if item["label"] == "Batiment")
    assert item["active"] and item["node_id"] == result["graph_node_ids"]["objects"][0]


def broken_link_card():
    payload = raw()
    payload["suggested_links"] = [{"source_label": payload["main_effect"]["label"],
        "target_existing_node_id": "missing", "relation_type": "concerne"}]
    return store(payload=payload)


def test_source_guard_keeps_missing_units_exceptions_and_blocks_auto_validation():
    text = "La voie mesure 4 m ; le recul est de 6,50 m, sauf extension existante."
    payload = raw()
    payload["main_effect"]["description"] = "Assurer une accessibilite adaptee."
    payload["rule_details"] = []
    payload["source_excerpt"] = ""
    checked = salience.preserve_source_checks([payload], text, 3, "source-id")[0]
    assert checked["source_checks"][0]["text"] == text
    assert checked["source_checks"][0]["document_id"] == "source-id"
    current = store(payload=checked, policy=ValidationSettings().model_dump())
    assert current["business_validation_status"] != "auto_validated"
    assert current["extraction_details"]["source_checks"][0]["text"] == text
    source = docs.get_document(current["document_id"])
    docs.purge_source(source["id"])
    archive = json.loads(exports.export_json(scope="all").read_text(encoding="utf-8"))
    assert archive["cards"][0]["extraction_details"]["source_checks"][0]["text"] == text


def test_source_guard_does_not_store_full_document_or_invent_evidence():
    text = "Introduction sans regle. " * 100 + "La distance est 5 m, sauf exception. " + "Suite sans regle. " * 100
    checked = salience.preserve_source_checks([raw()], text, 1)
    excerpts = checked[0]["source_checks"]
    assert len(excerpts) == 1
    assert len(excerpts[0]["text"]) <= 1200
    assert excerpts[0]["text"] == text[excerpts[0]["start"]:excerpts[0]["end"]]
    assert len(excerpts[0]["text"]) < len(text) / 2
    assert salience.preserve_source_checks([{**raw(), "source_checks": ["invented"]}], "Sans valeur ni exception precise.", 1)[0]["source_checks"][0]["text"] != "invented"


def test_source_guard_handles_empty_llm_response_without_losing_regulatory_passage():
    checked = salience.preserve_source_checks([], "Distance minimale 4 m.", 1)
    assert len(checked) == 1
    current = store(payload=checked[0], policy=ValidationSettings().model_dump())
    assert current["extraction_details"]["source_checks"]
    assert current["business_validation_status"] != "auto_validated"
    assert not graph.graph_payload()["nodes"]


def test_source_guard_does_not_duplicate_already_preserved_short_rule():
    text = "Distance minimale de 4 m, sauf extension."
    payload = raw()
    payload["rule_details"] = [text]
    checked = salience.preserve_source_checks([payload], text, 1)[0]
    assert not checked.get("source_checks")


def test_create_target_keeps_concept_and_link_outside_validated_graph():
    current = broken_link_card()
    cards.accept_card(current["id"])
    with TestClient(app) as client:
        response = client.post(f"/cards/{current['id']}/suggestions/{current['suggested_links'][0]['id']}/target", json={
            "source_node_id": current["graph_node_ids"]["effect"], "relation_type": "concerne", "label": "Hydrant"})
    assert response.status_code == 200, response.text
    link = response.json()
    assert link["status"] == "to_review" and link["can_accept"]
    node = graph.get_node(link["target_existing_node_id"])
    assert node["status"] == "to_confirm"
    assert node["id"] not in {item["id"] for item in graph.graph_payload()["nodes"]}


def test_explicit_target_creation_does_not_reactivate_rejected_concept():
    from app.models.schemas import KnowledgeNodeIn, SuggestionTargetCreate
    current = broken_link_card()
    rejected = graph.create_node(KnowledgeNodeIn(label="Hydrant", type="object", status="rejected"))
    result = coherence.create_suggestion_target(current["id"], current["suggested_links"][0]["id"], SuggestionTargetCreate(
        source_node_id=current["graph_node_ids"]["effect"], relation_type="concerne", label="Hydrant"))
    assert result["target_existing_node_id"] != rejected["id"]
    assert graph.get_node(rejected["id"])["status"] == "rejected"


@pytest.mark.parametrize("label,source_id", [("Voie d'acces", None), ("Hydrant", "missing")])
def test_create_target_rejects_duplicate_or_rolls_back_bad_repair(label, source_id):
    from app.models.schemas import SuggestionTargetCreate
    current = broken_link_card()
    before = knowledge_snapshot()
    with pytest.raises(ValueError):
        coherence.create_suggestion_target(current["id"], current["suggested_links"][0]["id"], SuggestionTargetCreate(
            source_node_id=source_id or current["graph_node_ids"]["effect"], relation_type="concerne", label=label))
    assert knowledge_snapshot() == before


@pytest.mark.parametrize("mode", ["sober", "balanced", "exhaustive"])
def test_prompt_preserves_rules_and_names_the_selected_mode(mode):
    prompt = build_analysis_prompt(title="Reglement", content_text="Recul 6 m", existing_nodes=[], extraction_mode=mode)
    assert f"Mode d'extraction : {mode}" in prompt
    assert "exceptions" in prompt and "salience_score" in prompt and "rule_details" in prompt
    assert "un identifiant invente" in prompt
