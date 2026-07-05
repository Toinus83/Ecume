from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from app.database.db import get_db, now_iso
from app.services import analysis_service
from app.services.document_service import get_document
from app.services.serialization import row_to_dict, rows_to_dicts


def start_analysis_job(document_id: str) -> dict[str, Any]:
    document = get_document(document_id)
    if not document:
        raise ValueError("Document introuvable.")
    job_id = str(uuid.uuid4())
    timestamp = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO analysis_jobs
            (id, document_id, status, progress, step, message, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        row = conn.execute("SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)).fetchone()
    asyncio.create_task(_run_analysis_job(job_id, document_id))
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
            "SELECT * FROM analysis_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
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
