from __future__ import annotations

import json
from typing import Any

import httpx

from app.llm.base import LLMProvider
from app.llm.prompt import build_analysis_prompt


class ApiLLMProvider(LLMProvider):
    """OpenAI-compatible chat completions provider."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def analyze_document(
        self,
        *,
        title: str,
        content_text: str,
        existing_nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.base_url or not self.api_key or not self.model:
            raise ValueError("Configuration API incomplète : URL, clé API et modèle sont requis.")
        prompt = build_analysis_prompt(
            title=title, content_text=content_text, existing_nodes=existing_nodes
        )
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ValueError(f"L'API LLM a refusé la requête : {response.text[:500]}") from exc
            payload = response.json()
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError("L'API LLM n'a pas renvoyé de contenu exploitable.")
        return json.loads(content)
