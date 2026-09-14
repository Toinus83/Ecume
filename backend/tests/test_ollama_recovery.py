import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.ollama import OllamaProvider

CUDA_ERROR = "llama-server process has terminated: CUDA error: the provided PTX was compiled with an unsupported toolchain."


def test_cuda_failure_retries_on_cpu_and_keeps_mode_for_next_chunk(monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(500, json={"error": CUDA_ERROR})
        return httpx.Response(200, json={"response": '{"cards": [], "warnings": []}'})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    async def run():
        provider = OllamaProvider(model="local-test-model", allow_cpu_fallback=True)
        first = await provider.analyze_document(title="", content_text="", existing_nodes=[])
        second = await provider.analyze_document(title="", content_text="", existing_nodes=[])
        assert first["warnings"] and second["warnings"]
    asyncio.run(run())
    assert len(requests) == 3
    assert "options" not in json.loads(requests[0].content)
    assert all(json.loads(request.content)["options"]["num_gpu"] == 0 for request in requests[1:])
    assert requests[1].extensions["timeout"]["read"] == 600
    assert requests[1].extensions["timeout"]["connect"] == 10


@pytest.mark.parametrize("detail", ["out of memory", "model load failed"])
def test_unrelated_failure_does_not_retry(detail):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(500, json={"error": detail})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            response = await OllamaProvider()._post(client, "http://ollama/api/generate", json={"model": "test"})
            assert response.status_code == 500
    asyncio.run(run())
    assert len(requests) == 1


def test_failed_cpu_retry_stops_after_two_attempts():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(500, json={"error": CUDA_ERROR})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            response = await OllamaProvider(allow_cpu_fallback=True)._post(client, "http://ollama/api/chat", json={"model": "test", "messages": []})
            assert response.status_code == 500
    asyncio.run(run())
    assert len(requests) == 2


def test_successful_gpu_request_has_no_cpu_override():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"response": "OK"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await OllamaProvider()._post(client, "http://ollama/api/generate", json={"model": "test"})
    asyncio.run(run())
    assert len(requests) == 1
    assert "options" not in json.loads(requests[0].content)


def test_cuda_error_does_not_silently_enable_cpu_by_default():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(500, json={"error": CUDA_ERROR})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(ValueError, match="Vulkan"):
                await OllamaProvider()._post(client, "http://ollama/api/generate", json={"model": "test"})
    asyncio.run(run())
    assert len(requests) == 1
    assert "options" not in json.loads(requests[0].content)
