from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.llm.api import ApiLLMProvider
from app.llm.errors import (
    LLMConfigurationError,
    LLMEndpointError,
    LLMModelNotFoundError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.llm.factory import provider_from_settings
from app.llm.json_payload import extract_json_object
from app.llm.ollama import OllamaProvider
from app.services import admin_service


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"cards": []}', {"cards": []}),
        ('```json\n{"cards": []}\n```', {"cards": []}),
        ('Voici le résultat : {"cards": []} Fin.', {"cards": []}),
    ],
)
def test_extract_json_object_accepts_common_model_responses(raw, expected):
    assert extract_json_object(raw) == expected


def test_extract_json_object_rejects_invalid_json():
    with pytest.raises(LLMResponseError, match="aucun objet JSON valide"):
        extract_json_object("```json\n{incomplet\n```")


def test_ollama_functional_test_checks_model_and_real_generation():
    requests = []

    def respond(request: httpx.Request):
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "test-model"}]})
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["format"] == "json"
        return httpx.Response(200, json={"response": '{"ecume_test":"ok"}'})

    provider = OllamaProvider(
        base_url="http://ollama:11434",
        model="test-model",
        transport=httpx.MockTransport(respond),
    )
    assert run(provider.functional_test()) == {"ecume_test": "ok"}
    assert [request.url.path for request in requests] == ["/api/tags", "/api/generate"]


def test_ollama_missing_model_never_uses_another_model():
    def respond(_request: httpx.Request):
        return httpx.Response(200, json={"models": [{"name": "another-model"}]})

    provider = OllamaProvider(model="configured-model", transport=httpx.MockTransport(respond))
    with pytest.raises(LLMModelNotFoundError, match="configured-model"):
        run(provider.functional_test())


def test_ollama_retries_without_native_json_only_when_unsupported():
    payloads = []

    def respond(request: httpx.Request):
        payloads.append(json.loads(request.content))
        if len(payloads) == 1:
            return httpx.Response(400, json={"error": "unsupported parameter: format"})
        return httpx.Response(200, json={"response": "```json\n{\"cards\": []}\n```"})

    provider = OllamaProvider(model="model", transport=httpx.MockTransport(respond))
    assert run(provider.generate_json("test")) == {"cards": []}
    assert payloads[0]["format"] == "json"
    assert "format" not in payloads[1]


def test_ollama_uses_chat_when_generate_endpoint_is_missing():
    paths = []

    def respond(request: httpx.Request):
        paths.append(request.url.path)
        if request.url.path == "/api/generate":
            return httpx.Response(404, json={"error": "route not found"})
        return httpx.Response(200, json={"message": {"content": '{"cards": []}'}})

    provider = OllamaProvider(model="model", transport=httpx.MockTransport(respond))
    assert run(provider.generate_json("test")) == {"cards": []}
    assert paths == ["/api/generate", "/api/chat"]


def test_ollama_timeout_has_clear_error():
    def respond(request: httpx.Request):
        raise httpx.ReadTimeout("slow", request=request)

    provider = OllamaProvider(model="slow", timeout_seconds=321, transport=httpx.MockTransport(respond))
    with pytest.raises(LLMTimeoutError, match="321"):
        run(provider.generate_json("test"))


def test_ollama_http_error_has_status_and_detail():
    def respond(_request: httpx.Request):
        return httpx.Response(500, json={"error": "model process stopped"})

    provider = OllamaProvider(model="model", transport=httpx.MockTransport(respond))
    with pytest.raises(LLMEndpointError, match="HTTP 500.*model process stopped"):
        run(provider.generate_json("test"))


def test_openai_compatible_generation_and_optional_api_key():
    requests = []

    def respond(request: httpx.Request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Texte {\"cards\": []} fin"}}]},
        )

    provider = ApiLLMProvider(
        base_url="http://llm.local",
        api_key="",
        model="generic-model",
        transport=httpx.MockTransport(respond),
    )
    assert run(provider.generate_json("test")) == {"cards": []}
    assert requests[0].url.path == "/v1/chat/completions"
    assert "authorization" not in requests[0].headers


def test_openai_compatible_retries_without_response_format():
    payloads = []

    def respond(request: httpx.Request):
        payloads.append(json.loads(request.content))
        if len(payloads) == 1:
            return httpx.Response(400, json={"error": {"message": "response_format is unsupported"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})

    provider = ApiLLMProvider(
        base_url="http://llm/v1",
        api_key="secret",
        model="model",
        transport=httpx.MockTransport(respond),
    )
    assert run(provider.generate_json("test")) == {"ok": True}
    assert "response_format" in payloads[0]
    assert "response_format" not in payloads[1]


def test_unknown_provider_is_rejected():
    with pytest.raises(LLMConfigurationError, match="non supporté"):
        provider_from_settings({"llm_enabled": True, "llm_provider": "unknown"})


def test_admin_test_runs_the_same_real_json_generation(monkeypatch):
    paths = []

    def respond(request: httpx.Request):
        paths.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "admin-model"}]})
        return httpx.Response(200, json={"response": '{"ecume_test":"ok"}'})

    provider = OllamaProvider(
        base_url="http://ollama",
        model="admin-model",
        transport=httpx.MockTransport(respond),
    )
    monkeypatch.setattr(
        admin_service.config,
        "get_llm_config",
        lambda: {"llm_enabled": True, "llm_provider": "ollama"},
    )
    monkeypatch.setattr(admin_service, "provider_from_settings", lambda _settings: provider)
    result = run(admin_service.test_llm_settings())
    assert result["ok"] is True
    assert "génération OK" in result["message"]
    assert result["available_models"] == ["admin-model"]
    assert paths == ["/api/tags", "/api/generate"]
