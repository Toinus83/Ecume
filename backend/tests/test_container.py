from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app import config
from app.database import db
from app.services import document_service, export_service
from app.web import create_app


@pytest.fixture
def single_origin(monkeypatch, tmp_path):
    data = tmp_path / "data"
    for name, value in {"DATA_DIR": data, "UPLOAD_DIR": data / "uploads",
                        "EXPORT_DIR": data / "exports", "DB_PATH": data / "ecume.db"}.items():
        monkeypatch.setattr(db, name, value)
    monkeypatch.setattr(document_service, "UPLOAD_DIR", data / "uploads")
    monkeypatch.setattr(export_service, "EXPORT_DIR", data / "exports")
    monkeypatch.setattr(config, "ENV_PATH", data / "settings.env")
    frontend = tmp_path / "frontend"
    (frontend / "assets").mkdir(parents=True)
    (frontend / "index.html").write_text('<html><div id="root"></div></html>', encoding="utf-8")
    (frontend / "assets" / "test.js").write_text("export const api = '/api';", encoding="utf-8")
    monkeypatch.setenv("ECUME_FRONTEND_DIR", str(frontend))
    return data


def test_single_origin_lifespan_static_and_existing_api(single_origin):
    assert not (single_origin / "ecume.db").exists()
    with TestClient(create_app()) as client:
        assert (single_origin / "ecume.db").exists()
        assert 'id="root"' in client.get("/").text
        assert "'/api'" in client.get("/assets/test.js").text
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/documents").json() == []
        assert client.get("/api/cards").json() == []
        assert client.get("/api/export/json").status_code == 200


@pytest.mark.parametrize("path", ["/.env", "/settings.env", "/ecume.db", "/backend/app/config.py",
                                      "/assets/missing.js", "/api/nonexistent"])
def test_single_origin_does_not_expose_data_or_mask_missing_paths(single_origin, path):
    with TestClient(create_app()) as client:
        response = client.get(path)
        assert response.status_code == 404
        assert 'id="root"' not in response.text


def test_single_origin_recreation_preserves_database(single_origin):
    with TestClient(create_app()) as client:
        node = client.post("/api/graph/nodes", json={"label": "Persistence check", "type": "object"}).json()
    with TestClient(create_app()) as client:
        assert node["id"] in {n["id"] for n in client.get("/api/graph?scope=all").json()["nodes"]}


def test_missing_frontend_fails_clearly(monkeypatch, tmp_path):
    monkeypatch.setenv("ECUME_FRONTEND_DIR", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="Frontend absent"):
        create_app()


def test_container_config_paths_and_admin_settings_survive_process_restart(tmp_path):
    managed_names = {
        *config.RDF_ENV_KEYS.values(), *config.RDF_ENV_ALIASES.values(),
        "LLM_ENABLED", "LLM_PROVIDER", "OLLAMA_BASE_URL", "OLLAMA_MODEL",
        "EXTERNAL_LLM_API_KEY", "EXTERNAL_LLM_BASE_URL", "EXTERNAL_LLM_MODEL",
        "LLM_API_KEY", "LLM_API_URL", "LLM_MODEL", "ECUME_ALLOW_LLM_FALLBACK",
    }
    environment = {key: value for key, value in os.environ.items() if key not in managed_names}
    environment.update({
        "ECUME_DATA_DIR": str(tmp_path / "data"),
        "ECUME_ENV_PATH": str(tmp_path / "data" / "settings.env"),
        "PYTHONPATH": str(ROOT / "backend"),
        "LLM_ENABLED": "true",
        "LLM_PROVIDER": "ollama",
        "OLLAMA_MODEL": "initial-kubernetes-model",
        "ECUME_FUSEKI_BASE_URL": "http://initial-fuseki:3030",
        "ECUME_ECHO_DEFAULT_DOMAIN": "ECHO_INITIAL",
        "ECUME_ONTOCAST_API_URL": "http://initial-ontocast",
        "ECUME_ONTOSPHERE_URL": "http://initial-ontosphere",
    })
    code = """
import json
from app import config
from app.database.db import init_db
init_db()
initial = {'model': config.get_llm_config()['ollama_model'], 'fuseki': config.get_rdf_config()['fuseki_base_url']}
config.save_llm_config({
    'llm_enabled': True, 'llm_provider': 'api',
    'external_llm_base_url': 'http://persisted-llm/v1',
    'external_llm_model': 'persisted-model',
    'external_llm_api_key': 'persisted-llm-secret'
})
config.save_rdf_config({
    'fuseki_enabled': True, 'fuseki_base_url': 'http://persisted-fuseki:3030',
    'fuseki_dataset': 'persisted-dataset', 'echo_source': 'fuseki',
    'echo_default_domain': 'ECHO_METEO',
    'echo_owl_reference': 'graph:echo:meteo:owl',
    'echo_voc_reference': 'graph:echo:meteo:voc',
    'echo_shacl_reference': 'graph:echo:meteo:shacl',
    'ontocast_enabled': True, 'ontocast_mode': 'api',
    'ontocast_api_url': 'http://persisted-ontocast/health',
    'ontocast_api_token': 'persisted-ontocast-secret',
    'ontosphere_enabled': True, 'ontosphere_url': 'http://persisted-ontosphere'
})
print(json.dumps({'db':str(config.DB_PATH), 'env':str(config.ENV_PATH), 'initial':initial}))
"""
    result = subprocess.run([sys.executable, "-c", code], env=environment, cwd=tmp_path,
                            check=True, text=True, capture_output=True)
    paths = json.loads(result.stdout)
    assert Path(paths["db"]) == tmp_path / "data" / "ecume.db"
    assert Path(paths["env"]) == tmp_path / "data" / "settings.env"
    assert paths["initial"] == {
        "model": "initial-kubernetes-model",
        "fuseki": "http://initial-fuseki:3030",
    }
    restart_code = """
import json
from app import config
from app.services import analysis_service, fuseki_service
llm = config.get_llm_config()
rdf = config.get_rdf_config()
provider = analysis_service._provider()
print(json.dumps({
    'llm_provider': llm['llm_provider'],
    'llm_url': provider.base_url,
    'llm_model': provider.model,
    'llm_secret_loaded': provider.api_key == 'persisted-llm-secret',
    'fuseki_url': fuseki_service._settings()['fuseki_base_url'],
    'fuseki_dataset': rdf['fuseki_dataset'],
    'echo_domain': rdf['echo_default_domain'],
    'echo_layers': [rdf['echo_owl_reference'], rdf['echo_voc_reference'], rdf['echo_shacl_reference']],
    'ontocast_url': rdf['ontocast_api_url'],
    'ontocast_secret_loaded': rdf['ontocast_api_token'] == 'persisted-ontocast-secret',
    'ontosphere_url': rdf['ontosphere_url'],
}))
"""
    result = subprocess.run([sys.executable, "-c", restart_code],
        env=environment, cwd=tmp_path, check=True, text=True, capture_output=True)
    restarted = json.loads(result.stdout)
    assert restarted == {
        "llm_provider": "api",
        "llm_url": "http://persisted-llm/v1",
        "llm_model": "persisted-model",
        "llm_secret_loaded": True,
        "fuseki_url": "http://persisted-fuseki:3030",
        "fuseki_dataset": "persisted-dataset",
        "echo_domain": "ECHO_METEO",
        "echo_layers": ["graph:echo:meteo:owl", "graph:echo:meteo:voc", "graph:echo:meteo:shacl"],
        "ontocast_url": "http://persisted-ontocast/health",
        "ontocast_secret_loaded": True,
        "ontosphere_url": "http://persisted-ontosphere",
    }


def packaging_module():
    spec = importlib.util.spec_from_file_location("package_offline", ROOT / "scripts" / "package-offline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_delivery_contains_only_public_instructions_and_image(tmp_path, monkeypatch):
    module = packaging_module()
    (tmp_path / "ecume-image.tar").write_bytes(b"synthetic image for manifest unit test")
    monkeypatch.setattr(module, "run", lambda *args, **kwargs: "abc123" if args[1] == "rev-parse" else "")
    module.write_delivery(tmp_path, "ecume:test", "linux/amd64", "sha256:test")
    assert {f.name for f in tmp_path.iterdir()} == {
        "ecume-image.tar", "compose.yaml", ".env.example", "README.md", "SHA256SUMS", "manifest.json"}
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["working_tree_dirty"] is False
    assert manifest["contains_llm_model"] is False
    assert manifest["image"] == "ecume:test"
    assert "ECUME_IMAGE=ecume:test" in (tmp_path / ".env.example").read_text()
    for filename, checksum in manifest["files_sha256"].items():
        assert module.sha256(tmp_path / filename) == checksum


def test_packaging_refuses_missing_docker(monkeypatch, tmp_path):
    module = packaging_module()
    monkeypatch.setattr(sys, "argv", ["package-offline.py", "--output", str(tmp_path / "delivery")])
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as failure:
        module.main()
    assert failure.value.code == 2
    assert not (tmp_path / "delivery").exists()


def test_packaging_never_overwrites_delivery(monkeypatch, tmp_path):
    module = packaging_module()
    monkeypatch.setattr(sys, "argv", ["package-offline.py", "--output", str(tmp_path)])
    with pytest.raises(SystemExit) as failure:
        module.main()
    assert failure.value.code == 2


def test_failed_smoke_test_never_produces_delivery(monkeypatch, tmp_path):
    module = packaging_module()
    monkeypatch.setattr(sys, "argv", ["package-offline.py", "--output", str(tmp_path / "delivery")])
    monkeypatch.setattr(module.shutil, "which", lambda _: "docker")
    calls = []
    def fake_run(*args, **kwargs):
        calls.append(args)
        return "linux" if args[1] == "info" else ""
    monkeypatch.setattr(module, "run", fake_run)
    def fail(*args):
        raise RuntimeError("smoke test failed")
    monkeypatch.setattr(module, "smoke_test", fail)
    with pytest.raises(RuntimeError, match="smoke test failed"):
        module.main()
    assert not (tmp_path / "delivery").exists()
    assert not any("save" in call for call in calls)


def test_split_container_and_kubernetes_artifacts_are_present_and_safe():
    expected = [
        "backend/Dockerfile",
        "frontend/Dockerfile",
        "frontend/docker/default.conf.template",
        "frontend/docker/40-runtime-config.sh",
        "docker-compose.yml",
        "k8s/namespace.yaml",
        "k8s/configmap.yaml",
        "k8s/secret.example.yaml",
        "k8s/pvc.yaml",
        "k8s/backend-deployment.yaml",
        "k8s/backend-service.yaml",
        "k8s/frontend-deployment.yaml",
        "k8s/frontend-service.yaml",
        "k8s/ingress.example.yaml",
        "k8s/README.md",
        "scripts/smoke-compose.py",
    ]
    assert all((ROOT / path).is_file() for path in expected)
    backend = (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "--reload" not in backend
    assert 'USER 10001:10001' in backend
    assert "ECUME_API_URL" in frontend
    assert "ecume-data:/data" in compose
    assert "LLM_ENABLED: ${LLM_ENABLED:-false}" in compose
    assert "ECUME_FUSEKI_ENABLED: ${FUSEKI_ENABLED:-false}" in compose


def test_runtime_api_config_and_local_fallback_are_both_supported():
    index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    client = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    runtime_script = (ROOT / "frontend/docker/40-runtime-config.sh").read_text(encoding="utf-8")
    assert '<script src="/config.js"></script>' in index
    assert index.index('<script src="/config.js"></script>') < index.index('<script type="module"')
    assert "window.__ECUME_CONFIG__?.apiBaseUrl" in client
    assert "http://127.0.0.1:8000" in client
    assert "ECUME_API_URL" in runtime_script


def test_local_kubernetes_secret_is_ignored():
    result = subprocess.run(
        ["git", "check-ignore", "-q", "k8s/secret.local.yaml"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0
