from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    async def analyze_document(
        self,
        *,
        title: str,
        content_text: str,
        existing_nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return the ECUME structured JSON analysis."""
