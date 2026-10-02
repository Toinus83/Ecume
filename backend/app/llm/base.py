from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    async def generate_json(self, prompt: str) -> dict[str, Any]:
        """Generate and parse one JSON object using the configured provider."""
        raise NotImplementedError

    async def list_models(self) -> list[str]:
        return []

    async def functional_test(self) -> dict[str, Any]:
        result = await self.generate_json(
            'Réponds uniquement avec ce petit objet JSON : {"ecume_test":"ok"}'
        )
        if result.get("ecume_test") != "ok":
            raise ValueError(
                "Le modèle génère du JSON, mais n'a pas respecté le test ECUME attendu."
            )
        return result

    @abstractmethod
    async def analyze_document(
        self,
        *,
        title: str,
        content_text: str,
        existing_nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return the ECUME structured JSON analysis."""
