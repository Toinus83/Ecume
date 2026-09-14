from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from test_mvp import isolated_data_dir
from test_documents import upload
from test_validation_workflows import analyzed, standalone
from app.database import db
from app.main import app
from app.models.schemas import CardUpdate, SuggestionRepair, ValidationSettings
from app.services import analysis_service as analysis, card_service as cards, coherence_service as coherence
from app.services import graph_service as graph, job_service as jobs, validation_service as validation, export_service as exports


def suggestion(card, target_id, source_label=None, relation="concerne"):
    coherence.save_suggestions({**card, "suggested_links": [{
        "source_label": source_label or card["main_effect"]["label"], "target_existing_node_id": target_id,
        "relation_type": relation, "confidence": "high", "reason": "Correspondance a controler",
    }]})
    return coherence.suggestions_for_card(card["id"])[-1]


@pytest.mark.parametrize("target", ["...", "missing-node", "", None])
def test_missing_target_is_visible_but_never_acceptable(target):
    current = analyzed(upload(), mode="strict")
    item = suggestion(current, target)
    assert not item["can_accept"]
    assert "incomplet" in item["invalid_reason"]
    before = len(graph.list_edges())
    with TestClient(app) as client:
        response = client.post(f"/cards/{current['id']}/suggestions/{item['id']}/decision", json={"status": "accepted"})
    assert response.status_code == 200
    assert response.json()["status"] == "to_review"
    assert not response.json()["can_accept"]
    assert len(graph.list_edges()) == before


def test_stale_target_removed_after_display_is_handled_as_review():
    current = analyzed(upload(), mode="strict")
    target = standalone("Cible")
    item = suggestion(current, target["id"])
    assert item["can_accept"]
    with db.get_db() as conn:
        conn.execute("DELETE FROM knowledge_nodes WHERE id = ?", (target["id"],))
    result = coherence.decide_suggestion(current["id"], item["id"], "accepted")
    assert result["status"] == "to_review"
    assert not result["can_accept"]


@pytest.mark.parametrize("case", ["source_missing", "target_rejected", "target_merged", "self", "relation"])
def test_unusable_suggestion_endpoints_are_blocked(case):
    current = analyzed(upload(), mode="strict")
    target = standalone("Cible")
    if case.startswith("target_"):
        with db.get_db() as conn:
            conn.execute("UPDATE knowledge_nodes SET status = ? WHERE id = ?", ("rejected" if case.endswith("rejected") else "linked", target["id"]))
    item = suggestion(current, current["graph_node_ids"]["effect"] if case == "self" else target["id"],
                      source_label="Source absente" if case == "source_missing" else None,
                      relation="inconnue" if case == "relation" else "concerne")
    assert not item["can_accept"]
    assert coherence.decide_suggestion(current["id"], item["id"], "accepted")["status"] == "to_review"


def test_repair_preserves_candidate_until_explicit_acceptance():
    current = analyzed(upload(), mode="strict")
    target = standalone("Cible")
    item = suggestion(current, "...", source_label="Source temporaire")
    repair = SuggestionRepair(source_node_id=current["graph_node_ids"]["effect"], target_node_id=target["id"], relation_type="concerne")
    with TestClient(app) as client:
        response = client.post(f"/cards/{current['id']}/suggestions/{item['id']}/repair", json=repair.model_dump())
    assert response.status_code == 200
    fixed = response.json()
    assert fixed["can_accept"] and fixed["status"] == "to_review"
    assert fixed["edge_id"] is None
    assert fixed["validation_decision"]["origin"] == "user"
    accepted = coherence.decide_suggestion(current["id"], item["id"], "accepted")
    assert accepted["status"] == "accepted"
    assert coherence.decide_suggestion(current["id"], item["id"], "accepted")["edge_id"] == accepted["edge_id"]


def test_invalid_repair_rolls_back():
    current = analyzed(upload(), mode="strict")
    item = suggestion(current, "...")
    with pytest.raises(ValueError, match="incomplet"):
        coherence.repair_suggestion(current["id"], item["id"], SuggestionRepair(
            source_node_id=current["graph_node_ids"]["effect"], target_node_id="absent", relation_type="concerne"))
    assert coherence.suggestions_for_card(current["id"])[0]["target_existing_node_id"] == "..."


@pytest.mark.parametrize("mode,expected", [("strict", "needs_user_validation"), ("assisted", "auto_validated"), ("automatic", "auto_validated")])
def test_explicit_reapply_to_undecided(mode, expected):
    current = analyzed(upload(), mode="strict")
    report = validation.apply_to_undecided([current["id"]], ValidationSettings(mode=mode).model_dump())
    assert report["counts"][expected] == 1
    result = analysis.get_card(current["id"])
    assert result["business_validation_status"] == expected
    assert result["validation_decision"]["policy"]["mode"] == mode
    assert result["archimate_mapping_status"] in {"candidate", "proposed_by_llm"}
    exported = json.loads(exports.export_json().read_text(encoding="utf-8"))
    assert bool(exported["cards"]) == (expected == "auto_validated")


@pytest.mark.parametrize("action", ["accepted", "rejected", "to_confirm", "corrected", "reopened"])
def test_reapply_never_overwrites_human_decisions(action):
    current = analyzed(upload(), mode="strict")
    if action == "corrected":
        cards.update_card(current["id"], CardUpdate(business_justification="Correction humaine"))
    else:
        cards.update_card(current["id"], CardUpdate(status="accepted" if action == "reopened" else action))
        if action == "reopened":
            cards.update_card(current["id"], CardUpdate(status="proposed"))
    before = analysis.get_card(current["id"])
    report = validation.apply_to_undecided([current["id"]], ValidationSettings(mode="automatic").model_dump())
    assert report["counts"]["human_decision"] == 1
    assert analysis.get_card(current["id"]) == before


def test_legacy_cards_without_score_are_unchanged_and_explained():
    current = analyzed(upload(), confidence=None, mode="strict")
    with db.get_db() as conn:
        conn.execute("UPDATE extracted_cards SET validation_decision = '{}', business_validation_status = 'proposed' WHERE id = ?", (current["id"],))
    before = analysis.get_card(current["id"])
    report = validation.apply_to_undecided([current["id"]], ValidationSettings(mode="automatic").model_dump())
    assert report["counts"]["missing_score"] == 1
    assert analysis.get_card(current["id"]) == before


def test_historical_human_trace_and_automatic_decisions_are_protected():
    current = analyzed(upload(), mode="strict")
    cards.update_card(current["id"], CardUpdate(status="proposed"))
    with db.get_db() as conn:
        conn.execute("UPDATE extracted_cards SET validation_decision = '{}' WHERE id = ?", (current["id"],))
    auto = analyzed(upload())
    report = validation.apply_to_undecided([current["id"], auto["id"]], ValidationSettings(mode="strict").model_dump())
    assert report["counts"]["human_decision"] == 1
    assert report["counts"]["already_decided"] == 1


def test_legacy_review_with_uncertain_history_is_protected():
    current = analyzed(upload(), mode="strict")
    with db.get_db() as conn:
        conn.execute("UPDATE extracted_cards SET validation_decision = '{}', business_validation_status = 'to_review' WHERE id = ?", (current["id"],))
    before = analysis.get_card(current["id"])
    report = validation.apply_to_undecided([current["id"]], ValidationSettings(mode="automatic").model_dump())
    assert report["counts"]["uncertain_history"] == 1
    assert analysis.get_card(current["id"]) == before


def test_reapply_preserves_extraction_blockers_and_missing_link_decisions():
    current = analyzed(upload(), ambiguities=["Regle ambigue"])
    report = validation.apply_to_undecided([current["id"]], ValidationSettings(mode="automatic").model_dump())
    assert report["counts"]["to_review"] == 1
    assert "incertitudes" in " ".join(analysis.get_card(current["id"])["validation_decision"]["blockers"])


def test_batch_reapplication_rolls_back_if_history_fails(monkeypatch):
    current = analyzed(upload(), mode="strict")
    before = analysis.get_card(current["id"])
    original = validation.record_change
    def fail_batch(**kwargs):
        if kwargs["entity_type"] == "validation_batch":
            raise RuntimeError("journal indisponible")
        original(**kwargs)
    monkeypatch.setattr(validation, "record_change", fail_batch)
    with pytest.raises(RuntimeError):
        validation.apply_to_undecided([current["id"]], ValidationSettings().model_dump())
    assert analysis.get_card(current["id"]) == before


def test_settings_defaults_explicit_reset_and_no_silent_migration():
    assert validation.get_settings() == ValidationSettings().model_dump()
    custom = ValidationSettings(mode="automatic", auto_threshold=1, review_threshold=.28)
    validation.save_settings(custom)
    db.init_db()
    assert validation.get_settings() == custom.model_dump()
    with TestClient(app) as client:
        response = client.put("/validation/settings", json={**custom.model_dump(), "auto_threshold": .9, "review_threshold": .6})
    assert response.status_code == 200
    assert response.json() == ValidationSettings(mode="automatic").model_dump()


def test_analysis_policy_is_frozen_at_enqueue_and_retry_is_idempotent(monkeypatch):
    document = upload()
    received = []
    async def fake_analyze(document_id, progress_callback, *, validation_policy, extraction_mode="sober"):
        received.append(validation_policy)
        return {"cards": [], "warnings": []}
    monkeypatch.setattr(analysis, "analyze_document", fake_analyze)
    async def run():
        explicit = ValidationSettings(mode="strict").model_dump()
        started = jobs.start_analysis_job(document["id"], explicit)
        duplicate = jobs.start_analysis_job(document["id"], ValidationSettings(mode="automatic").model_dump())
        assert duplicate["id"] == started["id"]
        validation.save_settings(ValidationSettings(mode="automatic", review_threshold=.28))
        await asyncio.gather(*list(jobs._tasks))
        assert jobs.get_job(started["id"])["metadata"]["validation_policy"] == explicit
        assert received == [explicit]
    asyncio.run(run())


def test_apply_api_is_scoped_and_validates_thresholds():
    first, other = analyzed(upload(), mode="strict"), analyzed(upload(), mode="strict")
    with TestClient(app) as client:
        assert client.post("/validation/apply", json={"card_ids": [first["id"]], "settings": {"review_threshold": .9, "auto_threshold": .6}}).status_code == 422
        response = client.post("/validation/apply", json={"card_ids": [first["id"], first["id"]], "settings": {"mode": "automatic"}})
    assert response.status_code == 200
    assert response.json()["counts"]["auto_validated"] == 1
    assert analysis.get_card(other["id"])["business_validation_status"] == "needs_user_validation"


def test_resolved_link_blocker_does_not_permanently_prevent_reapplication():
    current = analyzed(upload(), mode="strict")
    item = suggestion(current, "...")
    policy = ValidationSettings(mode="automatic").model_dump()
    assert validation.apply_to_undecided([current["id"]], policy)["counts"]["to_review"] == 1
    coherence.decide_suggestion(current["id"], item["id"], "ignored")
    assert validation.apply_to_undecided([current["id"]], policy)["counts"]["auto_validated"] == 1
    assert coherence.suggestions_for_card(current["id"])[0]["status"] == "ignored"


def test_legacy_confidence_does_not_break_valid_link_acceptance():
    current = analyzed(upload(), mode="strict")
    item = suggestion(current, standalone("Cible")["id"])
    with db.get_db() as conn:
        row = conn.execute("SELECT payload FROM link_suggestions WHERE id = ?", (item["id"],)).fetchone()
        payload = {**json.loads(row["payload"]), "confidence": "fort"}
        conn.execute("UPDATE link_suggestions SET payload = ? WHERE id = ?", (json.dumps(payload), item["id"]))
    assert coherence.decide_suggestion(current["id"], item["id"], "accepted")["status"] == "accepted"
