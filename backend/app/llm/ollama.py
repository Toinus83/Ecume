from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.llm.base import LLMProvider
from app.llm.prompt import build_analysis_prompt


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def analyze_document(
        self,
        *,
        title: str,
        content_text: str,
        existing_nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        prompt = build_analysis_prompt(
            title=title, content_text=content_text, existing_nodes=existing_nodes
        )
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            if _is_model_not_found(response):
                fallback_model = await _first_available_model(client, self.base_url, self.model)
                if fallback_model:
                    response = await client.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": fallback_model,
                            "prompt": prompt,
                            "stream": False,
                            "format": "json",
                        },
                    )
            if response.status_code == 404:
                model_error = _model_not_found_message(response, self.model)
                if model_error:
                    raise ValueError(model_error)
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "format": "json",
                    },
                )
            if _is_model_not_found(response):
                fallback_model = await _first_available_model(client, self.base_url, self.model)
                if fallback_model:
                    response = await client.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": fallback_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "stream": False,
                            "format": "json",
                        },
                    )
            if response.status_code == 404:
                model_error = _model_not_found_message(response, self.model)
                if model_error:
                    raise ValueError(model_error)
                raise ValueError(
                    "Le service répond sur "
                    f"{self.base_url}, mais ne ressemble pas à l'API Ollama attendue "
                    "(/api/generate ou /api/chat introuvable). Vérifie OLLAMA_BASE_URL."
                )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = _response_error_text(response)
                raise ValueError(f"Ollama a refusé la requête : {detail}") from exc
            payload = response.json()
        raw = payload.get("response") or (payload.get("message") or {}).get("content", "")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            raise ValueError("Ollama a répondu, mais le JSON est invalide.")


def _response_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
    except ValueError:
        pass
    return response.text[:500] or f"HTTP {response.status_code}"


def _model_not_found_message(response: httpx.Response, model: str) -> str | None:
    detail = _response_error_text(response).lower()
    if "model" in detail and ("not found" in detail or "pull" in detail):
        return (
            f"Le modèle Ollama '{model}' n'est pas disponible localement. "
            f"Lance `ollama pull {model}` ou change OLLAMA_MODEL dans le fichier .env."
        )
    return None


def _is_model_not_found(response: httpx.Response) -> bool:
    detail = _response_error_text(response).lower()
    return response.status_code == 404 and "model" in detail and (
        "not found" in detail or "pull" in detail
    )


async def _first_available_model(
    client: httpx.AsyncClient, base_url: str, configured_model: str
) -> str | None:
    try:
        response = await client.get(f"{base_url}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
    except Exception:
        return None
    for model in models:
        name = model.get("name") or model.get("model")
        if name and name != configured_model:
            return str(name)
    return None
