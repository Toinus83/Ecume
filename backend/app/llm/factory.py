from __future__ import annotations

from typing import Any

from app.config import get_llm_config
from app.llm.api import ApiLLMProvider
from app.llm.errors import LLMConfigurationError
from app.llm.heuristic import HeuristicProvider
from app.llm.ollama import OllamaProvider


def provider_from_settings(settings: dict[str, Any] | None = None):
    current = settings or get_llm_config()
    if not current["llm_enabled"]:
        return HeuristicProvider()

    timeout = int(current.get("llm_timeout_seconds", 600))
    json_mode = str(current.get("llm_json_mode", "auto"))
    provider = current["llm_provider"]
    if provider == "ollama":
        return OllamaProvider(
            base_url=str(current["ollama_base_url"]),
            model=str(current["ollama_model"]),
            timeout_seconds=timeout,
            json_mode=json_mode,
            endpoint=str(current.get("ollama_endpoint", "auto")),
        )
    if provider == "api":
        return ApiLLMProvider(
            base_url=str(current["external_llm_base_url"]),
            api_key=str(current["external_llm_api_key"]),
            model=str(current["external_llm_model"]),
            timeout_seconds=timeout,
            json_mode=json_mode,
        )
    raise LLMConfigurationError(f"Fournisseur LLM non supporté : {provider}")
