import os
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = ROOT_DIR


def _load_local_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ[key] = value


def _bool_env(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _update_local_env(values: dict[str, Any]) -> None:
    """Update managed keys without deleting unrelated local configuration."""
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    replacements = {
        key: str(value).replace("\r", "").replace("\n", "")
        for key, value in values.items()
    }
    rendered: list[str] = []
    seen: set[str] = set()
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in replacements:
                rendered.append(f"{key}={replacements[key]}")
                seen.add(key)
                continue
        rendered.append(line)
    if rendered and rendered[-1]:
        rendered.append("")
    rendered.extend(f"{key}={value}" for key, value in replacements.items() if key not in seen)
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text("\n".join(rendered).rstrip() + "\n", encoding="utf-8")
    if os.name != "nt":
        ENV_PATH.chmod(0o600)
    _load_local_env(ENV_PATH)


ENV_PATH = Path(os.getenv("ECUME_ENV_PATH", str(PROJECT_DIR / ".env")))
_load_local_env(ENV_PATH)

DATA_DIR = Path(os.getenv("ECUME_DATA_DIR") or os.getenv("DATA_DIR") or str(PROJECT_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
_database_url = os.getenv("DATABASE_URL", "").strip()
DB_PATH = (
    Path(_database_url.removeprefix("sqlite:///"))
    if _database_url.startswith("sqlite:///")
    else Path(_database_url)
    if _database_url
    else DATA_DIR / "ecume.db"
)

LLM_ENABLED = _bool_env("LLM_ENABLED", True)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", os.getenv("ECUME_LLM_PROVIDER", "ollama"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", os.getenv("ECUME_OLLAMA_BASE_URL", "http://localhost:11434"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("ECUME_OLLAMA_MODEL", "llama3.1"))
EXTERNAL_LLM_API_KEY = os.getenv("EXTERNAL_LLM_API_KEY", os.getenv("LLM_API_KEY", ""))
EXTERNAL_LLM_BASE_URL = os.getenv("EXTERNAL_LLM_BASE_URL", os.getenv("LLM_API_URL", ""))
EXTERNAL_LLM_MODEL = os.getenv("EXTERNAL_LLM_MODEL", os.getenv("LLM_MODEL", ""))
ALLOW_LLM_FALLBACK = os.getenv("ECUME_ALLOW_LLM_FALLBACK", "false").lower() in {
    "1",
    "true",
    "yes",
}
LLM_TIMEOUT_SECONDS = _int_env("LLM_TIMEOUT_SECONDS", 600)
LLM_JSON_MODE = os.getenv("LLM_JSON_MODE", "auto")
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "auto")


def get_llm_config(*, include_secret: bool = True) -> dict[str, str | bool | int]:
    _load_local_env(ENV_PATH)
    timeout_seconds = _int_env("LLM_TIMEOUT_SECONDS", 600)
    result: dict[str, str | bool | int] = {
        "llm_enabled": _bool_env("LLM_ENABLED", True),
        "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama3.1"),
        "external_llm_api_key": os.getenv("EXTERNAL_LLM_API_KEY", os.getenv("LLM_API_KEY", "")),
        "external_llm_base_url": os.getenv("EXTERNAL_LLM_BASE_URL", os.getenv("LLM_API_URL", "")),
        "external_llm_model": os.getenv("EXTERNAL_LLM_MODEL", os.getenv("LLM_MODEL", "")),
        "allow_llm_fallback": os.getenv("ECUME_ALLOW_LLM_FALLBACK", "false").lower()
        in {"1", "true", "yes"},
        "llm_timeout_seconds": max(30, min(timeout_seconds, 3600)),
        "llm_json_mode": os.getenv("LLM_JSON_MODE", "auto"),
        "ollama_endpoint": os.getenv("OLLAMA_ENDPOINT", "auto"),
    }
    if not include_secret:
        result["has_external_llm_api_key"] = bool(result["external_llm_api_key"])
        result["external_llm_api_key"] = ""
    return result


def save_llm_config(values: dict[str, str | bool | int]) -> dict[str, str | bool | int]:
    current = get_llm_config()
    incoming = dict(values)
    clear_secret = bool(incoming.pop("clear_external_llm_api_key", False))
    incoming.pop("has_external_llm_api_key", None)
    incoming_secret = str(incoming.get("external_llm_api_key", ""))
    current.update({key: value for key, value in incoming.items() if key in current})
    if clear_secret:
        current["external_llm_api_key"] = ""
    elif not incoming_secret:
        current["external_llm_api_key"] = get_llm_config()["external_llm_api_key"]
    env_values = {
        "LLM_ENABLED": str(current["llm_enabled"]).lower(),
        "LLM_PROVIDER": current["llm_provider"],
        "OLLAMA_BASE_URL": current["ollama_base_url"],
        "OLLAMA_MODEL": current["ollama_model"],
        "EXTERNAL_LLM_API_KEY": current["external_llm_api_key"],
        "EXTERNAL_LLM_BASE_URL": current["external_llm_base_url"],
        "EXTERNAL_LLM_MODEL": current["external_llm_model"],
        "ECUME_ALLOW_LLM_FALLBACK": str(current["allow_llm_fallback"]).lower(),
        "LLM_TIMEOUT_SECONDS": current["llm_timeout_seconds"],
        "LLM_JSON_MODE": current["llm_json_mode"],
        "OLLAMA_ENDPOINT": current["ollama_endpoint"],
    }
    _update_local_env(env_values)
    return get_llm_config(include_secret=False)


RDF_DEFAULTS: dict[str, Any] = {
    "fuseki_enabled": False,
    "fuseki_base_url": "http://localhost:3030",
    "fuseki_dataset": "ecume",
    "fuseki_query_endpoint": "/query",
    "fuseki_update_endpoint": "/update",
    "fuseki_write_mode": "disabled",
    "graph_echo_owl": "graph:echo:reference:owl",
    "graph_echo_voc": "graph:echo:reference:voc",
    "graph_echo_shacl": "graph:echo:reference:shacl",
    "graph_ecume_candidates": "graph:ecume:candidates",
    "graph_ecume_validated": "graph:ecume:validated",
    "graph_ecume_rejected": "graph:ecume:rejected",
    "graph_ecume_provenance": "graph:ecume:provenance",
    "graph_ecume_review": "graph:ecume:review",
    "echo_source": "unconfigured",
    "echo_default_domain": "ECHO_RH",
    "echo_owl_reference": "",
    "echo_voc_reference": "",
    "echo_shacl_reference": "",
    "ontocast_enabled": False,
    "ontocast_mode": "disabled",
    "ontocast_api_url": "",
    "ontocast_api_token": "",
    "ontocast_timeout": 120,
    "ontocast_extraction_profile": "default",
    "ontocast_use_fuseki": False,
    "ontocast_local_fallback": True,
    "ontosphere_enabled": False,
    "ontosphere_url": "",
    "ontosphere_sparql_url": "",
    "ontosphere_review_graph": "graph:ecume:review",
    "rdf_auth_type": "none",
    "rdf_auth_username": "",
    "rdf_auth_secret": "",
    "rdf_read_only": True,
    "rdf_write_candidates_only": True,
    "rdf_write_validated": False,
}


RDF_ENV_KEYS = {key: f"ECUME_{key.upper()}" for key in RDF_DEFAULTS}
RDF_ENV_ALIASES = {
    "fuseki_enabled": "FUSEKI_ENABLED",
    "fuseki_base_url": "FUSEKI_BASE_URL",
    "fuseki_dataset": "FUSEKI_DATASET",
    "fuseki_query_endpoint": "FUSEKI_QUERY_ENDPOINT",
    "fuseki_update_endpoint": "FUSEKI_UPDATE_ENDPOINT",
    "fuseki_write_mode": "FUSEKI_WRITE_MODE",
    "graph_echo_owl": "FUSEKI_GRAPH_ECHO_OWL",
    "graph_echo_voc": "FUSEKI_GRAPH_ECHO_VOC",
    "graph_echo_shacl": "FUSEKI_GRAPH_ECHO_SHACL",
    "graph_ecume_candidates": "FUSEKI_GRAPH_ECUME_CANDIDATES",
    "graph_ecume_validated": "FUSEKI_GRAPH_ECUME_VALIDATED",
    "graph_ecume_rejected": "FUSEKI_GRAPH_ECUME_REJECTED",
    "graph_ecume_provenance": "FUSEKI_GRAPH_ECUME_PROVENANCE",
    "graph_ecume_review": "FUSEKI_GRAPH_ECUME_REVIEW",
    "ontocast_enabled": "ONTOCAST_ENABLED",
    "ontocast_api_url": "ONTOCAST_API_URL",
    "ontocast_api_token": "ONTOCAST_TOKEN",
    "ontosphere_enabled": "ONTOSPHERE_ENABLED",
    "ontosphere_url": "ONTOSPHERE_URL",
}


def get_rdf_config(*, include_secret: bool = True) -> dict[str, Any]:
    _load_local_env(ENV_PATH)
    result: dict[str, Any] = {}
    for key, default in RDF_DEFAULTS.items():
        raw = os.getenv(RDF_ENV_KEYS[key])
        if raw is None and key in RDF_ENV_ALIASES:
            raw = os.getenv(RDF_ENV_ALIASES[key])
        if isinstance(default, bool):
            result[key] = str(raw if raw is not None else default).lower() in {"1", "true", "yes"}
        elif isinstance(default, int):
            try:
                result[key] = int(raw) if raw is not None else default
            except ValueError:
                result[key] = default
        else:
            result[key] = raw if raw is not None else default
    if not include_secret:
        result["has_rdf_auth_secret"] = bool(result["rdf_auth_secret"])
        result["rdf_auth_secret"] = ""
        result["has_ontocast_api_token"] = bool(result["ontocast_api_token"])
        result["ontocast_api_token"] = ""
    return result


def save_rdf_config(values: dict[str, Any]) -> dict[str, Any]:
    current = get_rdf_config()
    incoming = dict(values)
    for secret_name in ("rdf_auth_secret", "ontocast_api_token"):
        clear_secret = bool(incoming.pop(f"clear_{secret_name}", False))
        incoming.pop(f"has_{secret_name}", None)
        incoming_secret = str(incoming.get(secret_name, ""))
        if clear_secret:
            current[secret_name] = ""
        elif incoming_secret:
            current[secret_name] = incoming_secret
        incoming.pop(secret_name, None)
    current.update({key: value for key, value in incoming.items() if key in RDF_DEFAULTS})
    env_values = {
        RDF_ENV_KEYS[key]: str(current[key]).lower() if isinstance(current[key], bool) else current[key]
        for key in RDF_DEFAULTS
    }
    _update_local_env(env_values)
    return get_rdf_config(include_secret=False)
