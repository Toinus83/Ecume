from __future__ import annotations

import httpx

from app import config
from app.database.db import get_db
from app.models.schemas import LLMSettings


def get_llm_settings() -> dict:
    return config.get_llm_config()


def update_llm_settings(settings: LLMSettings) -> dict:
    return config.save_llm_config(settings.model_dump())


async def test_llm_settings() -> dict:
    settings = config.get_llm_config()
    provider = settings["llm_provider"]
    if provider == "ollama":
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(f"{settings['ollama_base_url']}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
        names = [model.get("name") or model.get("model") for model in models]
        configured = settings["ollama_model"]
        return {
            "ok": configured in names,
            "provider": "ollama",
            "message": (
                f"Modèle disponible : {configured}"
                if configured in names
                else f"Modèle configuré absent. Modèles disponibles : {', '.join(names) or 'aucun'}"
            ),
            "available_models": names,
        }
    if provider == "api":
        missing = []
        if not settings["external_llm_base_url"]:
            missing.append("URL API")
        if not settings["external_llm_api_key"]:
            missing.append("clé API")
        if not settings["external_llm_model"]:
            missing.append("modèle")
        return {
            "ok": not missing,
            "provider": "api",
            "message": "Configuration API complète." if not missing else f"Champs manquants : {', '.join(missing)}",
            "available_models": [],
        }
    return {"ok": False, "provider": provider, "message": "Fournisseur inconnu.", "available_models": []}


def reset_database(*, confirmation: str, delete_uploads: bool, delete_exports: bool) -> dict:
    if confirmation != "RESET ECUME":
        raise ValueError("Confirmation invalide. Saisis exactement RESET ECUME.")
    tables = [
        "knowledge_edges",
        "knowledge_node_aliases",
        "knowledge_nodes",
        "extracted_cards",
        "source_documents",
        "analysis_jobs",
        "change_log",
    ]
    with get_db() as conn:
        for table in tables:
            conn.execute(f"DELETE FROM {table}")

    deleted_uploads = _clean_directory(config.UPLOAD_DIR) if delete_uploads else 0
    deleted_exports = _clean_directory(config.EXPORT_DIR) if delete_exports else 0
    return {
        "ok": True,
        "message": "Base ECUME réinitialisée.",
        "deleted_uploads": deleted_uploads,
        "deleted_exports": deleted_exports,
    }


def _clean_directory(path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    deleted = 0
    for item in path.iterdir():
        if item.is_file():
            item.unlink()
            deleted += 1
    return deleted
