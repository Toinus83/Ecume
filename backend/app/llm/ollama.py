from __future__ import annotations

from typing import Any

import httpx

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL
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


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        *,
        allow_cpu_fallback: bool = False,
        timeout_seconds: int = 600,
        json_mode: str = "auto",
        endpoint: str = "auto",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self._cpu_only = False
        self.allow_cpu_fallback = allow_cpu_fallback
        self.timeout_seconds = timeout_seconds
        self.json_mode = json_mode
        self.endpoint = endpoint
        self.transport = transport
        self._available_models: list[str] | None = None

    def _client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(self.timeout_seconds, connect=min(10, self.timeout_seconds))
        return httpx.AsyncClient(timeout=timeout, transport=self.transport)

    def _validate(self) -> None:
        if not self.base_url or not self.model:
            raise LLMConfigurationError("Configuration Ollama incomplète : URL et modèle sont requis.")
        if self.json_mode not in {"auto", "native", "prompt"}:
            raise LLMConfigurationError(f"Mode JSON inconnu : {self.json_mode}")
        if self.endpoint not in {"auto", "generate", "chat"}:
            raise LLMConfigurationError(f"Endpoint Ollama inconnu : {self.endpoint}")

    async def _post(self, client: httpx.AsyncClient, url: str, *, json: dict) -> httpx.Response:
        payload = dict(json)
        if self._cpu_only:
            payload["options"] = {**payload.get("options", {}), "num_gpu": 0}
        try:
            response = await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                f"Timeout après {self.timeout_seconds} s pendant la génération Ollama du modèle '{self.model}'."
            ) from exc
        except httpx.RequestError as exc:
            raise LLMConnectionError(
                f"ECUME ne trouve pas Ollama à {self.base_url}. Vérifie qu'il est démarré et que l'URL est accessible."
            ) from exc
        if not self._cpu_only and response.is_error and _is_cuda_toolchain_error(response):
            if not self.allow_cpu_fallback:
                raise LLMEndpointError(
                    "Incompatibilité CUDA du GPU. Relance Ollama avec "
                    "scripts/start-ollama-gpu.ps1 -Restart pour utiliser Vulkan. "
                    "Le passage automatique sur processeur est désactivé."
                )
            self._cpu_only = True
            payload["options"] = {**payload.get("options", {}), "num_gpu": 0}
            try:
                response = await client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                raise LLMTimeoutError(
                    f"Timeout après {self.timeout_seconds} s pendant la génération Ollama sur processeur."
                ) from exc
            except httpx.RequestError as exc:
                raise LLMConnectionError(f"Connexion à Ollama interrompue à {self.base_url}.") from exc
        return response

    async def list_models(self) -> list[str]:
        self._validate()
        try:
            async with self._client() as client:
                response = await client.get(f"{self.base_url}/api/tags")
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Timeout pendant la lecture des modèles Ollama.") from exc
        except httpx.RequestError as exc:
            raise LLMConnectionError(
                f"ECUME ne trouve pas Ollama à {self.base_url}. Vérifie qu'il est démarré."
            ) from exc
        if response.status_code == 404:
            raise LLMEndpointError(
                f"Le service à {self.base_url} ne fournit pas l'API Ollama attendue (/api/tags)."
            )
        if not response.is_success:
            raise LLMEndpointError(
                f"Ollama refuse la liste des modèles (HTTP {response.status_code}) : {_response_error_text(response)}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise LLMResponseError("Ollama a renvoyé une liste de modèles invalide.") from exc
        if not isinstance(body, dict):
            raise LLMResponseError("Ollama a renvoyé une liste de modèles invalide.")
        models = body.get("models", [])
        self._available_models = [
            str(item.get("name") or item.get("model"))
            for item in models
            if isinstance(item, dict) and (item.get("name") or item.get("model"))
        ]
        return self._available_models

    async def functional_test(self) -> dict[str, Any]:
        names = self._available_models if self._available_models is not None else await self.list_models()
        if not any(_model_matches(self.model, name) for name in names):
            raise LLMModelNotFoundError(
                f"Le modèle Ollama '{self.model}' n'est pas disponible localement. "
                f"Installe-le avec `ollama pull {self.model}` ou choisis un modèle disponible."
            )
        return await super().functional_test()

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        self._validate()
        endpoints = [self.endpoint] if self.endpoint != "auto" else ["generate", "chat"]
        last_response: httpx.Response | None = None
        async with self._client() as client:
            for endpoint in endpoints:
                payload = self._payload(endpoint, prompt, native_json=self.json_mode in {"auto", "native"})
                response = await self._post(client, f"{self.base_url}/api/{endpoint}", json=payload)
                if _is_model_not_found(response):
                    raise LLMModelNotFoundError(
                        f"Le modèle Ollama '{self.model}' n'est pas disponible localement. "
                        f"Installe-le avec `ollama pull {self.model}` ou choisis un autre modèle."
                    )
                if response.status_code == 404 and endpoint != endpoints[-1]:
                    last_response = response
                    continue
                if (
                    self.json_mode == "auto"
                    and response.status_code in {400, 422}
                    and _unsupported_parameter(response, "format")
                ):
                    payload.pop("format", None)
                    response = await self._post(client, f"{self.base_url}/api/{endpoint}", json=payload)
                last_response = response
                break
        assert last_response is not None
        self._raise_for_response(last_response)
        try:
            body = last_response.json()
        except ValueError as exc:
            raise LLMResponseError("Ollama a renvoyé une réponse HTTP qui n'est pas du JSON.") from exc
        if not isinstance(body, dict):
            raise LLMResponseError("Ollama a renvoyé une réponse de génération invalide.")
        message = body.get("message")
        raw = body.get("response") or (message.get("content") if isinstance(message, dict) else None)
        result = extract_json_object(raw)
        if self._cpu_only:
            warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
            result["warnings"] = [
                *warnings,
                "Incompatibilité CUDA : analyse effectuée sur le processeur, plus lentement.",
            ]
        return result

    def _payload(self, endpoint: str, prompt: str, *, native_json: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "stream": False}
        if endpoint == "chat":
            payload["messages"] = [{"role": "user", "content": _json_prompt(prompt)}]
        else:
            payload["prompt"] = _json_prompt(prompt)
        if native_json:
            payload["format"] = "json"
        return payload

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = _response_error_text(response)
        if response.status_code == 404:
            raise LLMEndpointError(
                f"Le service répond à {self.base_url}, mais /api/generate et /api/chat sont indisponibles."
            )
        raise LLMEndpointError(f"Ollama a refusé la requête (HTTP {response.status_code}) : {detail}")

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


def _json_prompt(prompt: str) -> str:
    return f"{prompt}\n\nRéponds avec un unique objet JSON valide, sans commentaire ni Markdown."


def _response_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            return str(error.get("message") or error) if isinstance(error, dict) else str(error)
    except ValueError:
        pass
    return response.text[:500] or f"HTTP {response.status_code}"


def _is_cuda_toolchain_error(response: httpx.Response) -> bool:
    detail = _response_error_text(response).lower()
    return "cuda" in detail and "ptx" in detail and "unsupported toolchain" in detail


def _is_model_not_found(response: httpx.Response) -> bool:
    detail = _response_error_text(response).lower()
    return response.status_code == 404 and "model" in detail and (
        "not found" in detail or "pull" in detail
    )


def _unsupported_parameter(response: httpx.Response, parameter: str) -> bool:
    detail = _response_error_text(response).lower()
    return parameter.lower() in detail and any(
        word in detail
        for word in ("unsupported", "not support", "unknown", "unrecognized", "invalid parameter")
    )


def _model_matches(configured: str, available: str) -> bool:
    return configured == available or f"{configured}:latest" == available or configured == f"{available}:latest"
