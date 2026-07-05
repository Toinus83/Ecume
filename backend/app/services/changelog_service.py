from __future__ import annotations

import json
import uuid
from typing import Any

from app.database.db import get_db, now_iso
from app.services.serialization import rows_to_dicts


def record_change(
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    origin: str,
    source_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO change_log
            (id, entity_type, entity_id, action, origin, source_id, created_at, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                entity_type,
                entity_id,
                action,
                origin,
                source_id,
                now_iso(),
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )


def recent_changes(limit: int = 30) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM change_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return rows_to_dicts(rows)
