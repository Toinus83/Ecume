from __future__ import annotations

import json
import math
from collections import Counter
from typing import get_args

from app.database.db import atomic, get_db, now_iso
from app.models.schemas import BusinessCategory, RelationType, ValidationSettings
from app.services.changelog_service import record_change


def get_settings() -> dict:
    with get_db() as conn:
        return dict(conn.execute("SELECT mode, auto_threshold, review_threshold FROM validation_settings WHERE id = 1").fetchone())


@atomic
def save_settings(settings: ValidationSettings) -> dict:
    with get_db() as conn:
        conn.execute("UPDATE validation_settings SET mode = ?, auto_threshold = ?, review_threshold = ? WHERE id = 1",
                     (settings.mode, settings.auto_threshold, settings.review_threshold))
        record_change(entity_type="settings", entity_id="validation", action="changed", origin="user", details=settings.model_dump())
    return get_settings()


def score(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else None


def decide(confidence: float | None, settings: dict, blockers: list[str]) -> dict:
    if settings["mode"] == "strict":
        status = "needs_user_validation"
    elif confidence is None:
        status = "needs_user_validation"
    elif blockers:
        status = "to_review"
    elif settings["mode"] == "automatic":
        status = "auto_validated" if confidence >= settings["review_threshold"] else "to_review"
    elif confidence >= settings["auto_threshold"]:
        status = "auto_validated"
    elif confidence >= settings["review_threshold"]:
        status = "to_review"
    else:
        status = "needs_user_validation"
    reason = ("strict_mode" if settings["mode"] == "strict" else "missing_score" if confidence is None else
              "blockers" if blockers else "sufficient_score" if status == "auto_validated" else "insufficient_score")
    return {"status": status, "score": confidence, "policy": settings, "blockers": blockers, "reason": reason,
            "origin": "validation_policy", "rule_version": "2", "decided_at": now_iso()}


def reapplication_exclusion(card: dict) -> str | None:
    decision = card.get("validation_decision") or {}
    if decision.get("origin") not in {None, "validation_policy"} or card["business_validation_status"] in {
        "validated_by_user", "corrected_by_user", "rejected"
    }:
        return "human_decision"
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM change_log WHERE entity_type = 'card' AND entity_id = ? AND origin = 'user' LIMIT 1",
                        (card["id"],)).fetchone():
            return "human_decision"
    if card["status"] in {"accepted", "accepted_orphan", "rejected", "linked"} or card["business_validation_status"] == "auto_validated":
        return "already_decided"
    if (card["status"] == "to_confirm" or card["business_validation_status"] == "to_review") and decision.get("origin") != "validation_policy":
        return "uncertain_history"
    return None


@atomic
def apply_to_undecided(card_ids: list[str], settings: dict) -> dict:
    from app.services import analysis_service
    policy = ValidationSettings(**settings).model_dump()
    counts = {key: 0 for key in ("auto_validated", "to_review", "needs_user_validation", "missing_score",
                               "human_decision", "already_decided", "uncertain_history", "missing_card")}
    results = []
    for card_id in dict.fromkeys(card_ids):
        card = analysis_service.get_card(card_id)
        reason = reapplication_exclusion(card) if card else "missing_card"
        if not reason and score(card.get("business_confidence")) is None:
            reason = "missing_score"
        if reason:
            counts[reason] += 1
            results.append({"card_id": card_id, "outcome": "skipped", "reason": reason})
            continue
        raw = {"business_category": card["business_category"], "business_confidence": card["business_confidence"]}
        apply_to_new_card(card_id, raw, policy, card["warnings"], reapply=True)
        changed = analysis_service.get_card(card_id)
        outcome = changed["business_validation_status"]
        counts[outcome] += 1
        results.append({"card_id": card_id, "outcome": outcome, "reason": changed["validation_decision"].get("reason")})
    record_change(entity_type="validation_batch", entity_id=now_iso(), action="applied_to_undecided", origin="user",
                  details={"policy": policy, "counts": counts, "results": results})
    return {"policy": policy, "counts": counts, "results": results}


@atomic
def apply_to_new_card(card_id: str, raw: dict, settings: dict, warnings: list[str], *, reapply: bool = False) -> None:
    from app.services import analysis_service, coherence_service as coherence, graph_service
    card = analysis_service.get_card(card_id)
    if not card:
        return
    if reapply:
        if reapplication_exclusion(card):
            return
    elif card["status"] != "proposed" or card.get("validation_decision"):
        return
    confidence = score(raw.get("business_confidence"))
    blockers = []
    if card["level"] == "unknown":
        blockers.append("Niveau metier a qualifier")
    if raw.get("business_category") not in get_args(BusinessCategory) or card["business_category"] == "non_qualifie":
        blockers.append("Categorie metier a qualifier")
    if not card["main_effect"]["description"].strip():
        blockers.append("Description absente")
    if warnings or raw.get("ambiguities"):
        blockers.append("Analyse signalant des incertitudes")
    suggestions = coherence.suggestions_for_card(card_id)
    if card.get("extraction_details", {}).get("managed"):
        from app.services.salience_service import important_suggestions
        suggestions = important_suggestions(card, suggestions)
        threshold = settings["auto_threshold"] if settings["mode"] == "assisted" else settings["review_threshold"]
        if any(item.get("active") and (score(item.get("confidence")) is None or score(item.get("confidence")) < threshold)
               for item in card["extraction_details"].get("concepts", [])):
            blockers.append("Concept principal dont la comprehension reste a verifier")
    alternatives = Counter(item.get("source_node_id") for item in suggestions if item["status"] in {"proposed", "to_review"})
    if any(count > 1 for count in alternatives.values()):
        blockers.append("Plusieurs rapprochements possibles")
    if any(not item.get("can_accept") and item["status"] in {"proposed", "to_review"} for item in suggestions):
        blockers.append("Rapprochement incomplet a verifier")
    if reapply:
        # Preserve extraction uncertainties when the original LLM response is no longer available.
        old_blockers = card.get("validation_decision", {}).get("blockers", [])
        if "Analyse signalant des incertitudes" in old_blockers:
            blockers.append("Analyse signalant des incertitudes")
        blockers = list(dict.fromkeys(blockers))
    decision = decide(confidence, settings, blockers)
    business = decision["status"]
    legacy = "accepted" if business == "auto_validated" else "to_confirm" if business == "to_review" else "proposed"
    with get_db() as conn:
        conn.execute("""UPDATE extracted_cards SET status = ?, validation_status = ?, business_validation_status = ?,
            business_confidence = ?, validation_decision = ?, updated_at = ? WHERE id = ?""",
            (legacy, legacy, business, confidence, json.dumps(decision), now_iso(), card_id))
        record_change(entity_type="card", entity_id=card_id, action=business, origin="validation_policy",
                      source_id=card["document_id"], details=decision)
        coherence.refresh_states()
        if business == "auto_validated":
            for item in suggestions:
                link_score = score(item.get("business_confidence"))
                target = graph_service.get_node(item.get("target_existing_node_id") or "")
                if (item["status"] != "proposed" or not item.get("can_accept") or not target
                    or item.get("relation_type") not in get_args(RelationType)
                    or not coherence.is_valid(target) or alternatives[item["source_node_id"]] != 1
                    or item.get("ambiguities") or item["source_node_id"] == target["id"]):
                    continue
                link_decision = decide(link_score, settings, [])
                if link_decision["status"] == "auto_validated":
                    coherence.decide_suggestion(card_id, item["id"], "accepted", automatic_decision=link_decision)
