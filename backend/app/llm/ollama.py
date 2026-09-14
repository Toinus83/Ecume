from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.llm.base import LLMProvider
from app.llm.prompt import build_analysis_prompt


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL, *, allow_cpu_fallback: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._cpu_only = False
        self.allow_cpu_fallback = allow_cpu_fallback

    async def _post(self, client: httpx.AsyncClient, url: str, *, json: dict) -> httpx.Response:
        payload = dict(json)
        if self._cpu_only:
            payload["options"] = {**payload.get("options", {}), "num_gpu": 0}
        response = await client.post(url, json=payload, timeout=httpx.Timeout(600 if self._cpu_only else 120, connect=10))
        if not self._cpu_only and response.is_error and _is_cuda_toolchain_error(response):
            if not self.allow_cpu_fallback:
                raise ValueError(
                    "Incompatibilite CUDA du GPU. Relance Ollama avec "
                    "scripts/start-ollama-gpu.ps1 -Restart pour utiliser Vulkan. "
                    "Le passage automatique sur processeur est desactive."
                )
            self._cpu_only = True
            payload["options"] = {**payload.get("options", {}), "num_gpu": 0}
            response = await client.post(url, json=payload, timeout=httpx.Timeout(600, connect=10))
        return response

    async def analyze_document(
        self,
        *,
        title: str,
        content_text: str,
        existing_nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        prompt = build_analysis_prompt(
            title=title, content_text=content_text, existing_nodes=existing_nodes, extraction_mode=getattr(self, "extraction_mode", "sober")
        )
        async with httpx.AsyncClient(timeout=120) as client:
            response = await self._post(client,
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
                    response = await self._post(client,
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
                response = await self._post(client,
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
                    response = await self._post(client,
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
            result = json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                result = json.loads(raw[start : end + 1])
            else:
                raise ValueError("Ollama a répondu, mais le JSON est invalide.")
        if not isinstance(result, dict):
            raise ValueError("Ollama a répondu, mais la structure JSON est invalide.")
        if self._cpu_only:
            warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
            result["warnings"] = [*warnings, "Incompatibilite CUDA : analyse effectuee sur le processeur, plus lentement."]
        return result


def _response_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
    except ValueError:
        pass
    return response.text[:500] or f"HTTP {response.status_code}"


def _is_cuda_toolchain_error(response: httpx.Response) -> bool:
    detail = _response_error_text(response).lower()
    return "cuda" in detail and "ptx" in detail and "unsupported toolchain" in detail


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
