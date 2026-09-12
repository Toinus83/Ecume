from __future__ import annotations

import json

from app.database.db import get_db, now_iso
from app.models.schemas import CardUpdate
from app.semantic.archimate_mapping import infer_archimate_mapping
from app.services import graph_service
from app.services.analysis_service import get_card
from app.services.serialization import row_to_dict


def update_card(card_id: str, update: CardUpdate) -> dict:
    current = get_card(card_id)
    if not current:
        raise ValueError("Carte introuvable.")
    data = update.model_dump(exclude_unset=True)
    if "business_category" in data and "archimate_mapping" not in data:
        main_effect = data.get("main_effect") or current.get("main_effect") or {}
        label = main_effect.get("label", "") if isinstance(main_effect, dict) else ""
        data["archimate_mapping"] = infer_archimate_mapping(
            business_category=data["business_category"],
            concept_label=label,
            status="inferred_from_user_answer",
        )
        data.setdefault("archimate_mapping_status", "inferred_from_user_answer")
    fields = []
    params = []
    json_fields = {
        "main_effect",
        "objects",
        "actions",
        "conditions",
        "tasks",
        "suggested_links",
        "archimate_mapping",
    }
    for key, value in data.items():
        fields.append(f"{key} = ?")
        if key in json_fields:
            if hasattr(value, "model_dump"):
                value = value.model_dump()
            params.append(json.dumps(value, ensure_ascii=False))
        else:
            params.append(value)
    fields.append("updated_at = ?")
    params.append(now_iso())
    params.append(card_id)
    with get_db() as conn:
        conn.execute(f"UPDATE extracted_cards SET {', '.join(fields)} WHERE id = ?", params)
        row = conn.execute("SELECT * FROM extracted_cards WHERE id = ?", (card_id,)).fetchone()
    updated = row_to_dict(row)
    _sync_effect_node_semantics(updated)
    return updated


def accept_card(card_id: str, orphan: bool = False) -> dict:
    current = get_card(card_id)
    if not current:
        raise ValueError("Carte introuvable.")
    status = "accepted_orphan" if orphan else "accepted"
    node_ids = _all_card_node_ids(current)
    graph_service.update_node_status(node_ids, status)
    graph_service.update_card_edges_status(card_id, status)
    return update_card(
        card_id,
        CardUpdate(
            status=status,
            validation_status=status,
            business_validation_status="validated_by_user",
            archimate_mapping_status="inferred_from_user_answer",
        ),
    )


def merge_card(source_card_id: str, target_card_id: str) -> dict:
    source = get_card(source_card_id)
    target = get_card(target_card_id)
    if not source or not target:
        raise ValueError("Carte source ou cible introuvable.")
    merged = CardUpdate(
        objects=_merge_lists(target["objects"], source["objects"]),
        actions=_merge_lists(target["actions"], source["actions"]),
        conditions=_merge_lists(target["conditions"], source["conditions"]),
        tasks=_merge_lists(target["tasks"], source["tasks"]),
        suggested_links=[*target["suggested_links"], *source["suggested_links"]],
        status="to_confirm",
        validation_status="to_confirm",
    )
    updated = update_card(target_card_id, merged)
    update_card(source_card_id, CardUpdate(status="linked", validation_status="linked"))
    return updated


def _merge_lists(left: list[str], right: list[str]) -> list[str]:
    merged = []
    for item in [*left, *right]:
        if item not in merged:
            merged.append(item)
    return merged


def _all_card_node_ids(card: dict) -> list[str]:
    ids = []
    graph_ids = card.get("graph_node_ids") or {}
    for value in graph_ids.values():
        if isinstance(value, list):
            ids.extend(value)
        elif value:
            ids.append(value)
    return ids


def _sync_effect_node_semantics(card: dict) -> None:
    graph_ids = card.get("graph_node_ids") or {}
    effect_id = graph_ids.get("effect")
    if not effect_id or not isinstance(effect_id, str):
        return
    with get_db() as conn:
        conn.execute(
            """
            UPDATE knowledge_nodes
            SET business_category = ?,
                business_validation_status = ?,
                business_justification = ?,
                archimate_mapping = ?,
                archimate_mapping_status = ?,
                ontology_mapping_status = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                card.get("business_category", "non_qualifie"),
                card.get("business_validation_status", "proposed"),
                card.get("business_justification", ""),
                json.dumps(card.get("archimate_mapping", {}), ensure_ascii=False),
                card.get("archimate_mapping_status", ""),
                card.get("ontology_mapping_status", "to_map_later"),
                now_iso(),
                effect_id,
            ),
        )
