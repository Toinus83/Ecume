from __future__ import annotations

import copy
import json
import math
import re
import uuid

from app.database.db import atomic, get_db, now_iso
from app.services.changelog_service import record_change

ROLES = ("objects", "actions", "conditions", "tasks")
ROLE_LIMITS = {"objects": 5, "actions": 3, "conditions": 3, "tasks": 3}
MODE_LIMITS = {"sober": 4, "balanced": 8, "exhaustive": 14}


def key(value):
    from app.services.graph_service import _normalize
    return _normalize(str(value))


def score(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1 else None


def strings(values):
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip()))


def preserve_source_checks(raw_cards, chunk: str, chunk_index: int, document_id: str = "") -> list[dict]:
    """Preserve short source passages, not inferred rules or additional graph concepts."""
    cards = [copy.deepcopy(card) for card in raw_cards if isinstance(card, dict)] if isinstance(raw_cards, list) else []
    for card in cards:
        card.pop("source_checks", None)
    pattern = r"\b\d+(?:[.,]\d+)?\s*(?:m(?:[23\u00b2\u00b3])?(?:\s*/\s*h)?|m[\u00e8e]tres?|cm|mm|km|ha|heures?|minutes?|jours?|litres?)(?!\w)|\b\d+(?:[.,]\d+)?\s*%|\b(?:sauf|exception|except[\u00e9e]|d[\u00e9e]rogation|sous r[\u00e9e]serve|[\u00e0a] condition)\b"
    spans = []
    for match in re.finditer(pattern, chunk, flags=re.IGNORECASE):
        start, end = max(0, match.start() - 220), min(len(chunk), match.end() + 280)
        if spans and start <= spans[-1][1] and end - spans[-1][0] <= 1200:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    if not spans:
        return cards
    if not cards:
        cards = [{"main_effect": {"label": "Passages du document a verifier", "description": "Des regles ou valeurs sources restent a verifier avant de produire la connaissance."},
                  "business_category": "non_qualifie", "business_confidence": None}]
    def evidence(card):
        main = card.get("main_effect") or {}
        return key(" ".join([str(main.get("description", "") if isinstance(main, dict) else main),
                             *strings(card.get("rule_details")), str(card.get("source_excerpt") or "")]))
    for start, end in spans:
        excerpt = chunk[start:end]
        normalized = key(excerpt)
        if any(normalized in evidence(card) for card in cards):
            continue
        words = {word for word in normalized.split() if len(word) > 4}
        target = max(cards, key=lambda card: len(words & set(evidence(card).split())))
        target.setdefault("source_checks", []).append({"text": excerpt, "chunk_index": chunk_index, "document_id": document_id,
            "start": start, "end": end, "origin": "import", "status": "to_verify"})
        target["ambiguities"] = strings([*strings(target.get("ambiguities")), "Passages sources chiffres ou exceptions a verifier : ils ne sont pas entierement repris dans la synthese."])
    return cards


def prepare(raw: dict, mode: str) -> tuple[dict, dict]:
    """Keep evidence independently of the smaller set materialized as graph nodes."""
    if mode not in MODE_LIMITS:
        raise ValueError("Mode d'extraction invalide.")
    result = copy.deepcopy(raw)
    proposals, seen = [], set()
    for item in raw.get("concepts", []) if isinstance(raw.get("concepts"), list) else []:
        if not isinstance(item, dict) or item.get("role") not in ROLES:
            continue
        label = str(item.get("label") or "").strip()
        identity = (item["role"], key(label))
        if not label or identity in seen:
            continue
        seen.add(identity)
        importance = item.get("importance", "secondary")
        if importance not in {"principal", "secondary", "weak", "ignored"}:
            importance = "secondary"
        salience = score(item.get("salience_score"))
        reason = str(item.get("reason") or "").strip()
        # Missing scores are not converted into confident principal concepts.
        eligible = importance == "principal" and salience is not None and salience >= .65 and bool(reason)
        proposals.append({"id": str(uuid.uuid4()), "role": item["role"], "label": label,
                          "importance": "principal" if eligible else "secondary" if importance == "principal" else importance,
                          "salience_score": salience, "confidence": score(item.get("confidence")),
                          "reason": reason or "Importance non justifiee : a verifier.",
                          "source_excerpt": str(item.get("source_excerpt") or raw.get("source_excerpt") or "")[:1200],
                          "origin": "llm", "retained": False, "active": False, "node_id": None})
    for role in ROLES:
        for label in strings(raw.get(role)):
            if (role, key(label)) not in seen:
                seen.add((role, key(label)))
                proposals.append({"id": str(uuid.uuid4()), "role": role, "label": label,
                                  "importance": "secondary", "salience_score": None, "confidence": None,
                                  "reason": "Terme detecte sans qualification de son importance.",
                                  "source_excerpt": str(raw.get("source_excerpt") or "")[:1200],
                                  "origin": "import", "retained": False, "active": False, "node_id": None})
    ordered = sorted(proposals, key=lambda item: (-(item["salience_score"] or 0), key(item["label"])))
    selected = {role: [] for role in ROLES}
    total = 0
    for item in ordered:
        role = item["role"]
        if item["importance"] != "principal":
            continue
        if total < MODE_LIMITS[mode] and len(selected[role]) < ROLE_LIMITS[role]:
            selected[role].append(item["label"])
            item["active"] = True
            total += 1
        else:
            item["importance"] = "secondary"
            item["reason"] += " Conserve dans les details pour limiter la charge de validation."
    result.update(selected)
    details = {"version": 1, "managed": True, "include_theme": False, "mode": mode,
               "concepts": proposals, "rule_details": strings(raw.get("rule_details")),
               "ambiguities": strings(raw.get("ambiguities")),
               "source_checks": copy.deepcopy(raw.get("source_checks") or []),
               "source_excerpts": strings([raw.get("source_excerpt", ""), *strings(raw.get("source_excerpts"))]),
               "secondary_effects": strings(raw.get("secondary_effects"))}
    return result, details


def sync_bindings(card: dict) -> None:
    details = copy.deepcopy(card.get("extraction_details") or {})
    if not details.get("managed"):
        return
    proposals = details["concepts"]
    previously_active = {item["id"] for item in proposals if item.get("active")}
    for item in proposals:
        item.update(active=False, node_id=None)
    for role in ROLES:
        for label, node_id in zip(card[role], card["graph_node_ids"].get(role, [])):
            item = next((item for item in proposals if item["role"] == role and key(item["label"]) == key(label)), None)
            if item is None:
                item = {"id": str(uuid.uuid4()), "role": role, "label": label, "importance": "principal",
                        "salience_score": None, "confidence": None, "reason": "Concept ajoute explicitement par l'utilisateur.",
                        "source_excerpt": card.get("source_excerpt", ""), "origin": "user", "retained": True}
                proposals.append(item)
            if item["id"] not in previously_active and item["importance"] != "principal":
                item.update(importance="secondary", retained=True, origin="user")
            item.update(active=True, node_id=node_id)
    with get_db() as conn:
        conn.execute("UPDATE extracted_cards SET extraction_details = ? WHERE id = ?", (json.dumps(details, ensure_ascii=False), card["id"]))


@atomic
def decide_concept(card_id: str, proposal_id: str, action: str) -> dict:
    from app.services import card_service as cards
    from app.models.schemas import CardUpdate
    card = cards.require_card(card_id)
    details = copy.deepcopy(card.get("extraction_details") or {})
    item = next((item for item in details.get("concepts", []) if item["id"] == proposal_id), None)
    if not item or card["status"] in {"rejected", "linked"}:
        raise ValueError("Proposition indisponible. Remettez la carte a revoir si necessaire.")
    if action not in {"retain", "ignore"}:
        raise ValueError("Decision invalide.")
    if item.get("active"):
        raise ValueError("Ce concept est deja retenu. Utilisez Corriger pour le retirer de la carte.")
    before = copy.deepcopy(item)
    item.update(retained=action == "retain", importance="secondary" if action == "retain" else "ignored",
                origin="user", decided_at=now_iso())
    with get_db() as conn:
        conn.execute("UPDATE extracted_cards SET extraction_details = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(details, ensure_ascii=False), now_iso(), card_id))
    if action == "retain":
        cards.update_card(card_id, CardUpdate(**{item["role"]: [*card[item["role"]], item["label"]]}))
    record_change(entity_type="card", entity_id=card_id, action="concept_" + action, origin="user",
                  source_id=card["document_id"], details={"before": before, "proposal_id": proposal_id})
    return cards.require_card(card_id)


def node_importance() -> dict[str, str]:
    """Aggregate for search only; the persisted decision remains local to each card."""
    from app.services.serialization import row_to_dict
    result = {}
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM extracted_cards WHERE status NOT IN ('rejected', 'linked')").fetchall()
    for row in rows:
        card = row_to_dict(row)
        details = card.get("extraction_details") or {}
        if not details.get("managed"):
            continue
        main = card["graph_node_ids"].get("effect")
        if main:
            result[main] = "principal"
        for item in details.get("concepts", []):
            if item.get("active") and item.get("node_id"):
                node_id = item["node_id"]
                if result.get(node_id) != "principal":
                    result[node_id] = item["importance"]
    return result


def merge_details(source: dict, target: dict) -> None:
    incoming = source.get("extraction_details") or {}
    current = copy.deepcopy(target.get("extraction_details") or {})
    if not incoming.get("managed") and not current.get("managed"):
        return
    if not current.get("managed"):
        current = {"managed": True, "version": 1, "mode": "legacy_merge", "include_theme": True,
                   "concepts": [], "rule_details": [], "source_excerpts": []}
    existing = {(item["role"], key(item["label"])) for item in current["concepts"]}
    for item in incoming.get("concepts", []):
        identity = (item["role"], key(item["label"]))
        if identity not in existing:
            current["concepts"].append({**item, "id": str(uuid.uuid4()), "source_card_id": source["id"], "source_document_id": source["document_id"]})
            existing.add(identity)
    current["rule_details"] = strings([*current.get("rule_details", []), *incoming.get("rule_details", []), source["main_effect"].get("description", "")])
    current["ambiguities"] = strings([*current.get("ambiguities", []), *incoming.get("ambiguities", [])])
    checks = [*current.get("source_checks", []), *incoming.get("source_checks", [])]
    current["source_checks"] = list({json.dumps(check, sort_keys=True): check for check in checks}.values())
    current["source_excerpts"] = strings([*current.get("source_excerpts", []), *incoming.get("source_excerpts", []), source.get("source_excerpt", "")])
    with get_db() as conn:
        conn.execute("UPDATE extracted_cards SET extraction_details = ? WHERE id = ?", (json.dumps(current, ensure_ascii=False), target["id"]))


def important_suggestions(card: dict, suggestions: list[dict]) -> list[dict]:
    details = card.get("extraction_details") or {}
    if not details.get("managed"):
        return suggestions
    main_ids = {card["graph_node_ids"].get("effect"), *[item.get("node_id") for item in details.get("concepts", [])
                if item.get("active") and item["importance"] == "principal"]} - {None, ""}
    candidates = [item for item in suggestions if item.get("can_accept") and item.get("source_node_id") in main_ids
                  and item["status"] == "proposed" and (score(item.get("business_confidence")) or 0) >= .8]
    return sorted(candidates, key=lambda item: -(item.get("business_confidence") or 0))[:3]
