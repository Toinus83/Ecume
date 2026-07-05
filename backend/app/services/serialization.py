from __future__ import annotations

import json
import sqlite3
from typing import Any


JSON_FIELDS = {
    "metadata",
    "source_ids",
    "main_effect",
    "objects",
    "actions",
    "conditions",
    "tasks",
    "secondary_effects",
    "suggested_links",
    "warnings",
    "graph_node_ids",
    "details",
    "result_card_ids",
}


def loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for key in list(data):
        if key in JSON_FIELDS:
            default = [] if key.endswith("s") or key in {"suggested_links"} else {}
            data[key] = loads(data[key], default)
    return data


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in rows]
