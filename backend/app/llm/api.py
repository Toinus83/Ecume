from __future__ import annotations

from typing import Any

import httpx

from app.llm.base import LLMProvider
from app.llm.errors import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMEndpointError,
    LLMModelNotFoundError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.llm.json_payload import extract_json_object
from app.llm.prompt import build_analysis_prompt


class ApiLLMProvider(LLMProvider):
    """Provider for OpenAI-compatible chat completions APIs."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout_seconds: int = 600,
        json_mode: str = "auto",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.json_mode = json_mode
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(self.timeout_seconds, connect=min(10, self.timeout_seconds))
        return httpx.AsyncClient(timeout=timeout, transport=self.transport)

    def _validate(self) -> None:
        if not self.base_url or not self.model:
            raise LLMConfigurationError("Configuration API incomplète : URL et modèle sont requis.")
        if self.json_mode not in {"auto", "native", "prompt"}:
            raise LLMConfigurationError(f"Mode JSON inconnu : {self.json_mode}")

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        self._validate()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": _json_prompt(prompt)}],
        }
        if self.json_mode in {"auto", "native"}:
            payload["response_format"] = {"type": "json_object"}

        async with self._client() as client:
            response = await self._post(client, payload)
            if (
                self.json_mode == "auto"
                and response.status_code in {400, 422}
                and _unsupported_parameter(response, "response_format")
            ):
                payload.pop("response_format", None)
                response = await self._post(client, payload)
        self._raise_for_response(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMResponseError("L'API LLM a renvoyé une réponse HTTP qui n'est pas du JSON.") from exc
        choices = body.get("choices") if isinstance(body, dict) else None
        first_choice = choices[0] if isinstance(choices, list) and choices else None
        content = _message_content(first_choice.get("message", {})) if isinstance(first_choice, dict) else None
        return extract_json_object(content)

    async def _post(self, client: httpx.AsyncClient, payload: dict[str, Any]) -> httpx.Response:
        try:
            return await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Timeout après {self.timeout_seconds} s pendant la génération du modèle '{self.model}'."
            ) from exc
        except httpx.RequestError as exc:
            raise LLMConnectionError(
                f"Impossible de joindre l'API LLM à {self.base_url}. Vérifie l'URL et le réseau."
            ) from exc

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = _response_error_text(response)
        if self.api_key:
            detail = detail.replace(self.api_key, "***")
        lowered = detail.lower()
        if response.status_code == 404 and "model" in lowered:
            raise LLMModelNotFoundError(f"Le modèle '{self.model}' est introuvable sur l'API configurée.")
        if response.status_code in {401, 403}:
            raise LLMEndpointError("L'API LLM refuse l'authentification. Vérifie la clé ou les droits.")
        if response.status_code == 404:
            raise LLMEndpointError(
                f"Endpoint OpenAI-compatible introuvable : {self.base_url}/chat/completions."
            )
        raise LLMEndpointError(f"L'API LLM a refusé la requête (HTTP {response.status_code}) : {detail}")

    async def list_models(self) -> list[str]:
        self._validate()
        try:
            async with self._client() as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
            if not response.is_success:
                return []
            body = response.json()
            return [
                str(item["id"])
                for item in body.get("data", [])
                if isinstance(item, dict) and item.get("id")
            ]
        except (httpx.HTTPError, ValueError):
            return []

    async def analyze_document(
        self, *, title: str, content_text: str, existing_nodes: list[dict[str, Any]]
    ) -> dict[str, Any]:
        prompt = build_analysis_prompt(
            title=title,
            content_text=content_text,
            existing_nodes=existing_nodes,
            extraction_mode=getattr(self, "extraction_mode", "sober"),
            echo_context=getattr(self, "echo_context", ""),
            fill_mode=getattr(self, "fill_mode", None),
        )
        return await self.generate_json(prompt)


def _normalize_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    if not url:
        return ""
    path = url.split("://", 1)[-1].partition("/")[2]
    return url if path else f"{url}/v1"


def _json_prompt(prompt: str) -> str:
    return f"{prompt}\n\nRéponds avec un unique objet JSON valide, sans commentaire ni Markdown."


def _response_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)
            if error:
                return str(error)
            if payload.get("message"):
                return str(payload["message"])
    except ValueError:
        pass
    return response.text[:500] or f"HTTP {response.status_code}"


def _unsupported_parameter(response: httpx.Response, parameter: str) -> bool:
    detail = _response_error_text(response).lower()
    return parameter.lower() in detail and any(
        word in detail
        for word in ("unsupported", "not support", "unknown", "unrecognized", "invalid parameter")
    )


def _message_content(message: Any) -> Any:
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, list):
        return content
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)
