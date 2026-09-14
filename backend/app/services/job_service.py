from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from app.database.db import get_db, now_iso, transaction
from app.services import analysis_service
from app.services.document_service import get_document
from app.services.serialization import row_to_dict, rows_to_dicts

_tasks: set[asyncio.Task] = set()


def recover_interrupted_jobs() -> None:
    with transaction() as conn:
        timestamp = now_iso()
        conn.execute("""UPDATE analysis_jobs SET status = 'failed', step = 'interrupted',
            message = 'Analyse interrompue par un arret du backend.',
            error = 'Le backend a ete arrete. Relance l analyse depuis le document.',
            updated_at = ?, finished_at = ? WHERE status IN ('queued', 'running')""", (timestamp, timestamp))


def start_analysis_job(document_id: str, validation_settings: dict | None = None, *, extraction_mode: str = "sober") -> dict[str, Any]:
    from app.services.salience_service import MODE_LIMITS
    if extraction_mode not in MODE_LIMITS:
        raise ValueError("Mode d'extraction invalide.")
    document = get_document(document_id)
    if not document:
        raise ValueError("Document introuvable.")
    job_id = str(uuid.uuid4())
    timestamp = now_iso()
    from app.services.document_service import document_summary
    with transaction() as conn:
        active = conn.execute("SELECT * FROM analysis_jobs WHERE document_id = ? AND status IN ('queued', 'running')",
                              (document_id,)).fetchone()
        if active:
            return row_to_dict(active)
        if not document_summary(document_id)["can_reanalyze"]:
            raise ValueError("Source indisponible : fournis a nouveau le fichier avant de relancer l'analyse.")
        from app.models.schemas import ValidationSettings
        from app.services.validation_service import get_settings
        policy = ValidationSettings(**(validation_settings if validation_settings is not None else get_settings())).model_dump()
        conn.execute(
            """
            INSERT INTO analysis_jobs
            (id, document_id, status, progress, step, message, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                document_id,
                "queued",
                0,
                "queued",
                "Analyse ajoutée à la file de traitement.",
                timestamp,
                timestamp,
                json.dumps({"validation_policy": policy, "validation_rule_version": "2", "extraction_mode": extraction_mode}),
            ),
        )
        row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
    task = asyncio.create_task(_run_analysis_job(job_id, document_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return row_to_dict(row)


async def _run_analysis_job(job_id: str, document_id: str) -> None:
    _update_job(
        job_id,
        status="running",
        progress=5,
        step="starting",
        message="Le backend prépare l'analyse. Tu peux changer d'onglet.",
    )
    try:
        result = await analysis_service.analyze_document(
            document_id,
            progress_callback=lambda update: _update_job(job_id, status="running", **update),
            validation_policy=get_job(job_id)["metadata"].get("validation_policy"),
            extraction_mode=get_job(job_id)["metadata"].get("extraction_mode", "sober"),
        )
        card_ids = [card["id"] for card in result["cards"]]
        _update_job(
            job_id,
            status="completed",
            progress=100,
            step="completed",
            message=f"Analyse terminée : {len(card_ids)} carte(s) créée(s).",
            result_card_ids=card_ids,
            warnings=result.get("warnings", []),
            finished_at=now_iso(),
        )
        from app.services.document_service import get_document, purge_source
        document = get_document(document_id)
        if document and document["retention_policy"] == "purge_after_success":
            try:
                purge_source(document_id, origin="automatic_retention")
            except Exception as exc:
                _update_job(job_id, warnings=[*result.get("warnings", []), f"Analyse terminee, purge a reessayer : {exc}"])
    except asyncio.CancelledError:
        _update_job(job_id, status="failed", step="interrupted", message="Analyse interrompue.",
                    error="Le backend a ete arrete. Relance l'analyse.", finished_at=now_iso())
        raise
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            step="failed",
            message="Analyse interrompue.",
            error=str(exc),
            finished_at=now_iso(),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
    return row_to_dict(row) if row else None


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM analysis_jobs WHERE status IN ('queued', 'running') OR id IN
               (SELECT id FROM analysis_jobs ORDER BY created_at DESC LIMIT ?) ORDER BY created_at DESC""", (limit,)
        ).fetchall()
    return rows_to_dicts(rows)


def _update_job(job_id: str, **updates: Any) -> None:
    if not updates:
        return
    updates["updated_at"] = now_iso()
    json_fields = {"result_card_ids", "warnings", "metadata"}
    fields = []
    params = []
    for key, value in updates.items():
        fields.append(f"{key} = ?")
        if key in json_fields:
            params.append(json.dumps(value, ensure_ascii=False))
        else:
            params.append(value)
    params.append(job_id)
    with get_db() as conn:
        conn.execute(f"UPDATE analysis_jobs SET {', '.join(fields)} WHERE id = ?", params)
