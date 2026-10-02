from __future__ import annotations

import json
import re
from typing import Any

from app.llm.errors import LLMResponseError


_FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_json_object(value: Any) -> dict[str, Any]:
    """Return the first valid JSON object from a native or text response."""
    if isinstance(value, dict):
        return value
    if value is None:
        raise LLMResponseError("Le modèle a répondu sans contenu.")
    text = str(value).strip()
    if not text:
        raise LLMResponseError("Le modèle a répondu sans contenu.")

    candidates = [text, *_FENCED_JSON.findall(text)]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    raise LLMResponseError(
        "Le modèle a répondu, mais aucun objet JSON valide n'a pu être récupéré. "
        "Essaie le mode JSON automatique ou un autre modèle."
    )
