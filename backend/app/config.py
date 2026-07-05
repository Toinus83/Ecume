import os
from pathlib import Path


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


_load_local_env(PROJECT_DIR / ".env")

DATA_DIR = PROJECT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "ecume.db"
ENV_PATH = PROJECT_DIR / ".env"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", os.getenv("ECUME_LLM_PROVIDER", "ollama"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", os.getenv("ECUME_OLLAMA_BASE_URL", "http://localhost:11434"))
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("ECUME_OLLAMA_MODEL", "llama3.1"))
EXTERNAL_LLM_API_KEY = os.getenv("EXTERNAL_LLM_API_KEY", "")
EXTERNAL_LLM_BASE_URL = os.getenv("EXTERNAL_LLM_BASE_URL", "")
EXTERNAL_LLM_MODEL = os.getenv("EXTERNAL_LLM_MODEL", "")
ALLOW_LLM_FALLBACK = os.getenv("ECUME_ALLOW_LLM_FALLBACK", "false").lower() in {
    "1",
    "true",
    "yes",
}


def get_llm_config() -> dict[str, str | bool]:
    _load_local_env(ENV_PATH)
    return {
        "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama3.1"),
        "external_llm_api_key": os.getenv("EXTERNAL_LLM_API_KEY", ""),
        "external_llm_base_url": os.getenv("EXTERNAL_LLM_BASE_URL", ""),
        "external_llm_model": os.getenv("EXTERNAL_LLM_MODEL", ""),
        "allow_llm_fallback": os.getenv("ECUME_ALLOW_LLM_FALLBACK", "false").lower()
        in {"1", "true", "yes"},
    }


def save_llm_config(values: dict[str, str | bool]) -> dict[str, str | bool]:
    current = get_llm_config()
    current.update(values)
    env_values = {
        "LLM_PROVIDER": current["llm_provider"],
        "OLLAMA_BASE_URL": current["ollama_base_url"],
        "OLLAMA_MODEL": current["ollama_model"],
        "EXTERNAL_LLM_API_KEY": current["external_llm_api_key"],
        "EXTERNAL_LLM_BASE_URL": current["external_llm_base_url"],
        "EXTERNAL_LLM_MODEL": current["external_llm_model"],
        "ECUME_ALLOW_LLM_FALLBACK": str(current["allow_llm_fallback"]).lower(),
    }
    ENV_PATH.write_text(
        "\n".join(f"{key}={value}" for key, value in env_values.items()) + "\n",
        encoding="utf-8",
    )
    _load_local_env(ENV_PATH)
    return get_llm_config()
