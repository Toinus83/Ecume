from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from app.config import get_llm_config
from app.database.db import atomic, get_db, now_iso, transaction
from app.llm.heuristic import HeuristicProvider
from app.llm.factory import provider_from_settings
from app.models.schemas import KnowledgeEdgeIn, KnowledgeNodeIn, ManualCardRequest
from app.semantic.archimate_mapping import normalize_archimate_mapping, normalize_business_category
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


def _mapping_status(value: str | None) -> str:
    allowed = {
        "proposed_by_llm",
        "inferred_from_user_answer",
        "validated_by_user",
        "corrected_by_user",
        "validated_by_architect",
        "rejected",
        "to_review",
        "candidate",
        "unmapped",
        "to_map_later",
    }
    return value if value in allowed else "proposed_by_llm"


ProgressCallback = Callable[[dict[str, Any]], None]
CancelCheck = Callable[[], bool]


async def analyze_document(document_id: str, progress_callback: ProgressCallback | None = None, *, cancel_check: CancelCheck | None = None, validation_policy: dict | None = None, extraction_mode: str = "sober", fill_mode: str | None = None) -> dict:
    document = get_document(document_id)
    if not document:
        raise ValueError("Document introuvable.")
    if not document["content_text"].strip():
        raise ValueError("Texte source absent : fournis a nouveau le fichier.")
    if fill_mode is not None:
        from app.services.review_service import analyze
        provider = _provider()
        provider.extraction_mode = extraction_mode
        return await analyze(document, provider, _chunk_text(document['content_text']), fill_mode=fill_mode,
                             progress_callback=progress_callback, cancel_check=cancel_check)
    warnings: list[str] = []
    from app.services.validation_service import get_settings
    validation_policy = dict(validation_policy if validation_policy is not None else get_settings())
    all_cards: list[dict] = []
    chunks = _chunk_text(document["content_text"])
    provider = _provider()
    provider.extraction_mode = extraction_mode
    cancelled = False
    processed_chunks = 0
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
        if cancel_check and cancel_check():
            cancelled = True
            break
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
        from app.services.echo_workshop import extraction_context
        provider.echo_context = extraction_context(chunk)
        try:
            analysis = await provider.analyze_document(
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
        from app.services.salience_service import preserve_source_checks
        all_cards.extend(preserve_source_checks(analysis.get("cards") or [], chunk, index, document["id"]))
        processed_chunks = index
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
        if cancel_check and cancel_check():
            cancelled = True
            break

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
    with transaction():
        for raw_card in consolidated_cards:
            cards.append(_store_card(document, raw_card, warnings, validation_policy=validation_policy, extraction_mode=extraction_mode))
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
        action="analysis_cancelled" if cancelled else "analyzed",
        origin=f"llm:{get_llm_config()['llm_provider']}",
        source_id=document_id,
        details={"chunks": len(chunks), "chunks_processed": processed_chunks, "cards": len(cards),
                 "warnings": warnings, "cancelled": cancelled},
    )
    return {"document_id": document_id, "cards": cards, "warnings": warnings, "cancelled": cancelled}


def _provider():
    return provider_from_settings()


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
        if not isinstance(card, dict):
            continue
        main_effect = card.get("main_effect") or {}
        if not isinstance(main_effect, dict):
            main_effect = {"label": str(main_effect), "description": ""}
            card = {**card, "main_effect": main_effect}
        label = main_effect.get("label") if isinstance(main_effect, dict) else str(main_effect)
        normalized = " ".join(str(label).lower().split())
        from app.services.review_service import diagnostic
        if not normalized or diagnostic(normalized):
            continue
        if normalized in seen_labels:
            previous = next(item for item in consolidated if " ".join(str((item.get("main_effect") or {}).get("label", "")).lower().split()) == normalized)
            # Repeated titles across chunks must not discard distances, exceptions or sources.
            if isinstance(main_effect, dict):
                descriptions = list(dict.fromkeys([previous["main_effect"].get("description", ""), main_effect.get("description", "")]))
                previous["main_effect"]["description"] = "\n\n".join(value for value in descriptions if value)
            for field in ("objects", "actions", "conditions", "tasks", "secondary_effects", "rule_details", "business_rules", "concepts", "suggested_links", "ambiguities", "source_checks"):
                values = [*(previous.get(field) if isinstance(previous.get(field), list) else []), *(card.get(field) if isinstance(card.get(field), list) else [])]
                previous[field] = list({json.dumps(value, sort_keys=True, ensure_ascii=False): value for value in values}.values())
            from app.services.salience_service import strings, score
            scores = [score(previous.get("business_confidence")), score(card.get("business_confidence"))]
            previous["business_confidence"] = min(scores) if all(value is not None for value in scores) else None
            previous["source_excerpts"] = strings([*strings(previous.get("source_excerpts")), *strings(card.get("source_excerpts")), previous.get("source_excerpt", ""), card.get("source_excerpt", "")])
            continue
        seen_labels.add(normalized)
        consolidated.append(card)
    return consolidated


@atomic
def _store_card(document: dict, raw_card: dict[str, Any], warnings: list[str], *, validation_policy: dict | None = None, extraction_mode: str | None = None) -> dict:
    extraction_details = {}
    if 'simple_fields' in raw_card:
        from app.services.business_rule_service import extract
        fields = raw_card['simple_fields']
        raw_card = {**raw_card, 'objects': []}
        extraction_details = {'managed':True, 'include_theme':False, 'simple_fields':fields, 'concepts':[],
                              'business_rules':raw_card.get('business_rules',[]) or extract(raw_card), 'force_new':raw_card.get('force_new',False)}
    if extraction_mode is not None:
        from app.services.salience_service import prepare
        raw_card, extraction_details = prepare(raw_card, extraction_mode)
        from app.services.business_rule_service import verify_sources
        rule_warnings=verify_sources(extraction_details.get('business_rules',[]),document)
        if rule_warnings and raw_card.get('business_rules'):
            raw_card['ambiguities']=[*raw_card.get('ambiguities',[]),*rule_warnings]
            extraction_details['ambiguities']=[*extraction_details.get('ambiguities',[]),*rule_warnings]
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
    business_category = normalize_business_category(
        raw_card.get("business_category"),
        fallback="resultat_recherche",
    )
    business_justification = str(
        raw_card.get("business_justification")
        or raw_card.get("justification")
        or "Categorie metier proposee automatiquement par ECUME."
    ).strip()
    archimate_mapping = normalize_archimate_mapping(
        raw_card.get("archimate_mapping"),
        business_category=business_category,
        concept_label=main_effect["label"],
        document_type=document.get("file_type", ""),
        default_status="proposed_by_llm",
    )
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
        "business_category": business_category,
        "business_validation_status": "proposed",
        "business_justification": business_justification,
        "archimate_mapping": archimate_mapping,
        "archimate_mapping_status": _mapping_status(
            str(raw_card.get("archimate_mapping_status") or archimate_mapping.get("status"))
        ),
        "ontology_mapping_status": "to_map_later",
        "source_excerpt": str(raw_card.get("source_excerpt") or document["content_text"][:700])[:1200],
        "warnings": warnings,
        "graph_node_ids": {},
        "extraction_details": extraction_details,
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
             business_category, business_validation_status, business_justification,
             archimate_mapping, archimate_mapping_status, ontology_mapping_status,
             source_excerpt, warnings, graph_node_ids, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                payload["business_category"],
                payload["business_validation_status"],
                payload["business_justification"],
                json.dumps(payload["archimate_mapping"], ensure_ascii=False),
                payload["archimate_mapping_status"],
                payload["ontology_mapping_status"],
                payload["source_excerpt"],
                json.dumps(payload["warnings"], ensure_ascii=False),
                json.dumps(payload["graph_node_ids"], ensure_ascii=False),
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        row = conn.execute("SELECT * FROM extracted_cards WHERE id = ?", (card_id,)).fetchone()
    from app.services.coherence_service import bind_concepts, bind_relation, save_suggestions, refresh_states
    with get_db() as conn:
        conn.execute("UPDATE extracted_cards SET extraction_details = ? WHERE id = ?", (json.dumps(extraction_details, ensure_ascii=False), card_id))
    card = {**row_to_dict(row), "extraction_details": extraction_details}
    bind_concepts(card)
    with get_db() as conn:
        for edge in conn.execute("SELECT id FROM knowledge_edges WHERE json_extract(metadata, '$.card_id') = ?", (card_id,)):
            bind_relation(card_id, edge["id"])
    save_suggestions(card)
    refresh_states()
    if validation_policy is not None:
        from app.services.validation_service import apply_to_new_card
        apply_to_new_card(card_id, raw_card, validation_policy, warnings)
    return get_card(card_id)


@atomic
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
        "business_category": "resultat_recherche",
        "business_justification": "Carte creee manuellement, categorie par defaut a corriger si besoin.",
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
            business_category=card["business_category"],
            business_validation_status=card["business_validation_status"],
            business_justification=card["business_justification"],
            archimate_mapping=card["archimate_mapping"],
            archimate_mapping_status=card["archimate_mapping_status"],
            ontology_mapping_status=card["ontology_mapping_status"],
            metadata={"card_id": card["id"], "source_excerpt": card["source_excerpt"], "origin": "import", "force_new":card.get('extraction_details',{}).get('force_new',False)},
        )
    )
    _append_dedupe_suggestions(card, card["main_effect"]["label"], effect)
    node_ids["effect"] = effect["id"]
    if 'simple_fields' in card.get('extraction_details', {}):
        from app.services.review_graph import materialize_fields
        node_ids['theme'] = ''
        node_ids['objects'] = materialize_fields(card, effect['id'])
        return node_ids
    if card.get("extraction_details", {}).get("managed"):
        node_ids["theme"] = ""
    else:
        node_ids["theme"] = _materialize_theme(document, card, effect["id"])
    for field, node_type, relation in [
        ("objects", "object", "concerne"),
        ("actions", "action", "déclenche"),
        ("conditions", "condition", "nécessite"),
        ("tasks", "task", "se décompose en"),
    ]:
        for label in card[field]:
            proposal = next((item for item in card.get("extraction_details", {}).get("concepts", []) if item["role"] == field and item["label"] == label), {})
            node = graph_service.create_node(KnowledgeNodeIn(
                label=label, type=node_type, level="unknown", status="proposed", confidence=card["confidence"], source_ids=source_ids,
                description=proposal.get("reason", ""),
                **graph_service.default_semantic_fields_for_node(node_type=node_type, label=label, document_type=document.get("file_type", "")),
                metadata={"card_id": card["id"], "origin": "import", "source_excerpt": proposal.get("source_excerpt", card["source_excerpt"])},
            ))
            _append_dedupe_suggestions(card, label, node)
            node_ids[field].append(node["id"])
            graph_service.create_edge(KnowledgeEdgeIn(source_node_id=effect["id"], target_node_id=node["id"], relation_type=relation,
                label=relation, status="proposed", confidence=card["confidence"], source_ids=source_ids,
                metadata={"card_id": card["id"], "origin": "import"}))
    return node_ids


def _materialize_theme(document: dict, card: dict, effect_id: str) -> str:
    source_ids = [document["id"]]
    theme = graph_service.create_node(
        KnowledgeNodeIn(
            label=card["theme_label"],
            type="theme",
            description="Thème détecté dans le document.",
            level="unknown",
            status="proposed",
            confidence=card["confidence"],
            source_ids=source_ids,
            **graph_service.default_semantic_fields_for_node(
                node_type="theme",
                label=card["theme_label"],
                document_type=document.get("file_type", ""),
            ),
            metadata={"card_id": card["id"], "origin": "import"},
        )
    )
    graph_service.create_edge(
        KnowledgeEdgeIn(
            source_node_id=effect_id,
            target_node_id=theme["id"],
            relation_type="concerne",
            label="concerne",
            status="proposed",
            confidence=card["confidence"],
            source_ids=source_ids,
            metadata={"card_id": card["id"], "origin": "import"},
        )
    )
    return theme["id"]


def _append_dedupe_suggestions(card: dict, incoming_label: str, node: dict) -> None:
    dedupe = node.get("dedupe")
    if not dedupe:
        return
    for candidate in dedupe.get("candidates", []):
        if candidate["id"] == node["id"]:
            continue
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
    from app.services.coherence_service import suggestions_for_card
    cards = rows_to_dicts(rows)
    for card in cards:
        card["suggested_links"] = suggestions_for_card(card["id"])
    return cards


def get_card(card_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM extracted_cards WHERE id = ?", (card_id,)).fetchone()
    if not row:
        return None
    from app.services.coherence_service import suggestions_for_card
    card = row_to_dict(row)
    card["suggested_links"] = suggestions_for_card(card_id)
    return card
