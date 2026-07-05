from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from app.config import get_llm_config
from app.database.db import get_db, now_iso
from app.llm.api import ApiLLMProvider
from app.llm.heuristic import HeuristicProvider
from app.llm.ollama import OllamaProvider
from app.models.schemas import KnowledgeEdgeIn, KnowledgeNodeIn, ManualCardRequest
from app.services.changelog_service import record_change
from app.services import graph_service
from app.services.document_service import get_document
from app.services.serialization import row_to_dict, rows_to_dicts


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        if isinstance(value, dict):
            label = value.get("label") or value.get("name") or value.get("description")
        else:
            label = value
        if label and str(label).strip():
            cleaned.append(str(label).strip())
    return cleaned[:16]


def _confidence(value: str | None) -> str:
    return value if value in {"low", "medium", "high"} else "medium"


def _level(value: str | None) -> str:
    return value if value in {"strategic", "operational", "tactical", "operator", "unknown"} else "unknown"


ProgressCallback = Callable[[dict[str, Any]], None]


async def analyze_document(document_id: str, progress_callback: ProgressCallback | None = None) -> dict:
    document = get_document(document_id)
    if not document:
        raise ValueError("Document introuvable.")
    warnings: list[str] = []
    all_cards: list[dict] = []
    chunks = _chunk_text(document["content_text"])
    if progress_callback:
        progress_callback(
            {
                "step": "chunking",
                "message": f"{len(chunks)} partie(s) à analyser.",
                "progress": 10,
                "total_chunks": len(chunks),
            }
        )
    for index, chunk in enumerate(chunks, start=1):
        if progress_callback:
            progress_callback(
                {
                    "step": "llm_analysis",
                    "message": f"Analyse LLM de la partie {index}/{len(chunks)}.",
                    "current_chunk": index,
                    "total_chunks": len(chunks),
                    "progress": 10 + int((index - 1) / max(len(chunks), 1) * 65),
                }
            )
        existing_nodes = graph_service.existing_nodes_for_prompt()
        try:
            analysis = await _provider().analyze_document(
                title=f"{document['title']} - partie {index}/{len(chunks)}",
                content_text=chunk,
                existing_nodes=existing_nodes,
            )
        except Exception as exc:
            settings = get_llm_config()
            if not settings["allow_llm_fallback"]:
                raise ValueError(
                    "Analyse LLM impossible. Vérifie la configuration LLM dans l'onglet Admin, puis réessaie l'analyse. "
                    f"Détail technique : {exc}"
                ) from exc
            fallback = HeuristicProvider()
            analysis = await fallback.analyze_document(
                title=f"{document['title']} - partie {index}/{len(chunks)}",
                content_text=chunk,
                existing_nodes=existing_nodes,
            )
            warnings.append(f"Analyse heuristique utilisée sur la partie {index} : {exc}")
        warnings.extend(analysis.get("warnings") or [])
        all_cards.extend(analysis.get("cards") or [])
        if progress_callback:
            progress_callback(
                {
                    "step": "llm_analysis",
                    "message": f"Partie {index}/{len(chunks)} analysée.",
                    "current_chunk": index,
                    "total_chunks": len(chunks),
                    "progress": 10 + int(index / max(len(chunks), 1) * 65),
                }
            )

    cards = []
    consolidated_cards = _consolidate_cards(all_cards)
    if progress_callback:
        progress_callback(
            {
                "step": "card_generation",
                "message": f"{len(consolidated_cards)} carte(s) consolidée(s), sauvegarde en cours.",
                "progress": 80,
            }
        )
    for raw_card in consolidated_cards:
        cards.append(_store_card(document, raw_card, warnings))
    if progress_callback:
        progress_callback(
            {
                "step": "saving",
                "message": "Cartes et graphe sauvegardés.",
                "progress": 95,
            }
        )
    record_change(
        entity_type="document",
        entity_id=document_id,
        action="analyzed",
        origin=f"llm:{get_llm_config()['llm_provider']}",
        source_id=document_id,
        details={"chunks": len(chunks), "cards": len(cards), "warnings": warnings},
    )
    return {"document_id": document_id, "cards": cards, "warnings": warnings}


def _provider():
    settings = get_llm_config()
    if settings["llm_provider"] == "ollama":
        return OllamaProvider(
            base_url=str(settings["ollama_base_url"]),
            model=str(settings["ollama_model"]),
        )
    if settings["llm_provider"] == "api":
        base_url = str(settings["external_llm_base_url"]).rstrip("/")
        if base_url and not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return ApiLLMProvider(
            base_url=base_url,
            api_key=str(settings["external_llm_api_key"]),
            model=str(settings["external_llm_model"]),
        )
    raise ValueError(f"Fournisseur LLM non supporté : {settings['llm_provider']}")


def _chunk_text(text: str, max_chars: int = 7000, overlap: int = 500) -> list[str]:
    clean = text.strip()
    if len(clean) <= max_chars:
        return [clean]
    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + max_chars)
        split_at = clean.rfind("\n\n", start, end)
        if split_at <= start + 1000:
            split_at = end
        chunks.append(clean[start:split_at].strip())
        if split_at >= len(clean):
            break
        start = max(0, split_at - overlap)
    return [chunk for chunk in chunks if chunk]


def _consolidate_cards(raw_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    consolidated: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for card in raw_cards:
        main_effect = card.get("main_effect") or {}
        label = main_effect.get("label") if isinstance(main_effect, dict) else str(main_effect)
        normalized = " ".join(str(label).lower().split())
        if not normalized:
            continue
        if normalized in seen_labels:
            continue
        seen_labels.add(normalized)
        consolidated.append(card)
    return consolidated


def _store_card(document: dict, raw_card: dict[str, Any], warnings: list[str]) -> dict:
    card_id = str(uuid.uuid4())
    timestamp = now_iso()
    main_effect = raw_card.get("main_effect") or {}
    if isinstance(main_effect, str):
        main_effect = {"label": main_effect, "description": "", "level": "unknown", "confidence": "medium"}
    main_effect = {
        "label": str(main_effect.get("label") or raw_card.get("theme_label") or "Effet à qualifier").strip(),
        "description": str(main_effect.get("description") or "").strip(),
        "level": _level(main_effect.get("level")),
        "confidence": _confidence(main_effect.get("confidence")),
    }
    level = _level(raw_card.get("level") or main_effect["level"])
    payload = {
        "id": card_id,
        "document_id": document["id"],
        "theme_label": str(raw_card.get("theme_label") or document["title"]).strip(),
        "main_effect": main_effect,
        "level": level,
        "objects": _clean_list(raw_card.get("objects")),
        "actions": _clean_list(raw_card.get("actions")),
        "conditions": _clean_list(raw_card.get("conditions")),
        "tasks": _clean_list(raw_card.get("tasks")),
        "secondary_effects": _clean_list(raw_card.get("secondary_effects")),
        "suggested_links": raw_card.get("suggested_links") if isinstance(raw_card.get("suggested_links"), list) else [],
        "confidence": _confidence(raw_card.get("confidence") or main_effect["confidence"]),
        "status": "proposed",
        "validation_status": "proposed",
        "source_excerpt": str(raw_card.get("source_excerpt") or document["content_text"][:700]),
        "warnings": warnings,
        "graph_node_ids": {},
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    payload["graph_node_ids"] = _materialize_proposed_graph(document, payload)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO extracted_cards
            (id, document_id, theme_label, main_effect, level, objects, actions, conditions,
             tasks, secondary_effects, suggested_links, confidence, status, validation_status,
             source_excerpt, warnings, graph_node_ids, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["id"],
                payload["document_id"],
                payload["theme_label"],
                json.dumps(payload["main_effect"], ensure_ascii=False),
                payload["level"],
                json.dumps(payload["objects"], ensure_ascii=False),
                json.dumps(payload["actions"], ensure_ascii=False),
                json.dumps(payload["conditions"], ensure_ascii=False),
                json.dumps(payload["tasks"], ensure_ascii=False),
                json.dumps(payload["secondary_effects"], ensure_ascii=False),
                json.dumps(payload["suggested_links"], ensure_ascii=False),
                payload["confidence"],
                payload["status"],
                payload["validation_status"],
                payload["source_excerpt"],
                json.dumps(payload["warnings"], ensure_ascii=False),
                json.dumps(payload["graph_node_ids"], ensure_ascii=False),
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        row = conn.execute("SELECT * FROM extracted_cards WHERE id = ?", (card_id,)).fetchone()
    return row_to_dict(row)


def create_manual_card(request: ManualCardRequest) -> dict:
    document = get_document(request.document_id) if request.document_id else None
    if not document:
        document = _manual_source_document(request.source_excerpt)
    raw_card = {
        "theme_label": request.theme_label,
        "main_effect": request.main_effect.model_dump(),
        "level": request.level,
        "objects": request.objects,
        "actions": request.actions,
        "conditions": request.conditions,
        "tasks": request.tasks,
        "secondary_effects": [],
        "suggested_links": [],
        "source_excerpt": request.source_excerpt,
        "confidence": request.main_effect.confidence,
    }
    card = _store_card(document, raw_card, ["Carte créée manuellement."])
    record_change(
        entity_type="card",
        entity_id=card["id"],
        action="created",
        origin="user",
        source_id=document["id"],
        details={"theme_label": request.theme_label},
    )
    return card


def _manual_source_document(source_excerpt: str) -> dict:
    document_id = str(uuid.uuid4())
    timestamp = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO source_documents
            (id, title, filename, file_type, content_text, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                "Saisie manuelle",
                "manual-entry",
                "manual",
                source_excerpt or "Carte créée manuellement.",
                timestamp,
                json.dumps({"origin": "user"}, ensure_ascii=False),
            ),
        )
        row = conn.execute("SELECT * FROM source_documents WHERE id = ?", (document_id,)).fetchone()
    return row_to_dict(row)


def _materialize_proposed_graph(document: dict, card: dict) -> dict[str, Any]:
    source_ids = [document["id"]]
    node_ids: dict[str, Any] = {"objects": [], "actions": [], "conditions": [], "tasks": []}
    effect = graph_service.create_node(
        KnowledgeNodeIn(
            label=card["main_effect"]["label"],
            type="effect",
            description=card["main_effect"]["description"],
            level=card["level"],
            status="proposed",
            confidence=card["confidence"],
            source_ids=source_ids,
            metadata={"card_id": card["id"], "source_excerpt": card["source_excerpt"], "origin": "import"},
        )
    )
    _append_dedupe_suggestions(card, card["main_effect"]["label"], effect)
    node_ids["effect"] = effect["id"]
    theme = graph_service.create_node(
        KnowledgeNodeIn(
            label=card["theme_label"],
            type="theme",
            description="Thème détecté dans le document.",
            level="unknown",
            status="proposed",
            confidence=card["confidence"],
            source_ids=source_ids,
            metadata={"card_id": card["id"], "origin": "import"},
        )
    )
    node_ids["theme"] = theme["id"]
    graph_service.create_edge(
        KnowledgeEdgeIn(
            source_node_id=effect["id"],
            target_node_id=theme["id"],
            relation_type="concerne",
            label="concerne",
            status="proposed",
            confidence=card["confidence"],
            source_ids=source_ids,
            metadata={"card_id": card["id"], "origin": "import"},
        )
    )
    for field, node_type, relation in [
        ("objects", "object", "concerne"),
        ("actions", "action", "déclenche"),
        ("conditions", "condition", "nécessite"),
        ("tasks", "task", "se décompose en"),
    ]:
        for label in card[field]:
            node = graph_service.create_node(
                KnowledgeNodeIn(
                    label=label,
                    type=node_type,
                    level="unknown",
                    status="proposed",
                    confidence=card["confidence"],
                    source_ids=source_ids,
                    metadata={"card_id": card["id"], "origin": "import"},
                )
            )
            _append_dedupe_suggestions(card, label, node)
            node_ids[field].append(node["id"])
            graph_service.create_edge(
                KnowledgeEdgeIn(
                    source_node_id=effect["id"],
                    target_node_id=node["id"],
                    relation_type=relation,
                    label=relation,
                    status="proposed",
                    confidence=card["confidence"],
                    source_ids=source_ids,
                    metadata={"card_id": card["id"], "origin": "import"},
                )
            )
    for suggested in card["suggested_links"]:
        target_id = suggested.get("target_existing_node_id")
        if target_id:
            graph_service.create_edge(
                KnowledgeEdgeIn(
                    source_node_id=effect["id"],
                    target_node_id=target_id,
                    relation_type=suggested.get("relation_type") or "proche de",
                    label=suggested.get("relation_type") or "proche de",
                    status="to_confirm",
                    confidence=_confidence(suggested.get("confidence")),
                    source_ids=source_ids,
                    metadata={"card_id": card["id"], "reason": suggested.get("reason", ""), "origin": "import"},
                )
            )
    return node_ids


def _append_dedupe_suggestions(card: dict, incoming_label: str, node: dict) -> None:
    dedupe = node.get("dedupe")
    if not dedupe:
        return
    for candidate in dedupe.get("candidates", []):
        card["suggested_links"].append(
            {
                "source_label": incoming_label,
                "target_existing_node_id": candidate["id"],
                "target_label": candidate["label"],
                "relation_type": "proche de",
                "confidence": "medium",
                "reason": f"{candidate['match_kind']} détecté avant création du concept.",
            }
        )


def list_cards() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM extracted_cards ORDER BY created_at DESC").fetchall()
    return rows_to_dicts(rows)


def get_card(card_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM extracted_cards WHERE id = ?", (card_id,)).fetchone()
    return row_to_dict(row) if row else None
