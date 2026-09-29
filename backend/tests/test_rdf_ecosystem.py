from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import config
from app.llm.heuristic import HeuristicProvider
from app.main import app
from app.services import analysis_service, fuseki_service
from test_mvp import isolated_data_dir


@pytest.fixture(autouse=True)
def isolated_rdf_settings(monkeypatch: pytest.MonkeyPatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_PATH", env_path)
    for env_name in config.RDF_ENV_KEYS.values():
        monkeypatch.delenv(env_name, raising=False)


def test_fuseki_disabled_keeps_local_mode_and_never_calls_network():
    assert fuseki_service.is_enabled() is False
    assert asyncio.run(fuseki_service.run_select_query("SELECT * WHERE { ?s ?p ?o }")) == []
    assert asyncio.run(fuseki_service.find_close_concepts("Maire", "ECHO_RH")) == []
    health = asyncio.run(fuseki_service.health_check())
    assert health == {"ok": False, "enabled": False, "message": "Fuseki n'est pas activé. ECUME reste en mode local."}


def test_rdf_admin_masks_secret_and_preserves_llm_configuration():
    payload = config.get_rdf_config(include_secret=False)
    payload.pop("has_rdf_auth_secret")
    payload.update({"rdf_auth_type": "bearer", "rdf_auth_secret": "secret-never-returned"})
    with TestClient(app) as client:
        response = client.put("/admin/rdf", json=payload)
        assert response.status_code == 200
        saved = response.json()
        assert saved["rdf_auth_secret"] == ""
        assert saved["has_rdf_auth_secret"] is True
        fetched = client.get("/admin/rdf").json()
    assert fetched["rdf_auth_secret"] == ""
    assert "secret-never-returned" not in str(fetched)

    config.save_llm_config({"ollama_model": "modele-test"})
    assert config.get_rdf_config()["rdf_auth_secret"] == "secret-never-returned"
    assert config.get_llm_config()["ollama_model"] == "modele-test"


def test_close_match_contract_contains_traceable_fields(monkeypatch: pytest.MonkeyPatch):
    settings = {**config.RDF_DEFAULTS, "fuseki_enabled": True}
    monkeypatch.setattr(fuseki_service, "is_enabled", lambda: True)
    monkeypatch.setattr(fuseki_service, "_settings", lambda: settings)

    async def fake_query(_query: str):
        return [{
            "uri": "urn:echo:maire",
            "label": "Maire",
            "alt": "le maire",
            "graph": "graph:echo:reference:voc",
        }]

    monkeypatch.setattr(fuseki_service, "run_select_query", fake_query)
    matches = asyncio.run(fuseki_service.find_close_concepts("le maire", "ECHO_RH"))
    assert matches == [{
        "uri": "urn:echo:maire",
        "label": "Maire",
        "source_graph": "graph:echo:reference:voc",
        "source": "Echo via Fuseki",
        "match_type": "altLabel",
        "score": 0.94,
        "reason": "Synonyme exact dans le vocabulaire Echo.",
        "domain": "ECHO_RH",
    }]


def test_rdf_admin_tests_are_non_blocking_when_disabled():
    with TestClient(app) as client:
        connection = client.post("/admin/rdf/test/connection")
        query = client.post("/admin/rdf/test/query")
        exports = client.get("/export/json")
    assert connection.status_code == 200 and connection.json()["enabled"] is False
    assert query.status_code == 200 and query.json()["ok"] is False
    assert exports.status_code == 200


def test_llm_disabled_uses_local_analysis_without_network(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    settings = config.get_llm_config()
    assert settings["llm_enabled"] is False
    assert isinstance(analysis_service._provider(), HeuristicProvider)
    with TestClient(app) as client:
        fetched = client.get("/admin/llm")
        tested = client.post("/admin/llm/test")
    assert fetched.status_code == 200
    assert fetched.json()["llm_enabled"] is False
    assert tested.status_code == 200
    assert tested.json() == {
        "ok": True,
        "provider": "heuristic",
        "message": "LLM désactivé : ECUME utilise l'analyse locale simple.",
        "available_models": [],
    }


def test_generic_service_environment_aliases_are_accepted(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FUSEKI_ENABLED", "true")
    monkeypatch.setenv("FUSEKI_BASE_URL", "http://fuseki-alias:3030")
    monkeypatch.setenv("FUSEKI_DATASET", "alias-dataset")
    monkeypatch.setenv("ONTOCAST_ENABLED", "true")
    monkeypatch.setenv("ONTOCAST_API_URL", "http://ontocast-alias")
    monkeypatch.setenv("ONTOSPHERE_URL", "http://ontosphere-alias")
    settings = config.get_rdf_config()
    assert settings["fuseki_enabled"] is True
    assert settings["fuseki_base_url"] == "http://fuseki-alias:3030"
    assert settings["fuseki_dataset"] == "alias-dataset"
    assert settings["ontocast_enabled"] is True
    assert settings["ontocast_api_url"] == "http://ontocast-alias"
    assert settings["ontosphere_url"] == "http://ontosphere-alias"
