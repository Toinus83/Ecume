from __future__ import annotations

import httpx

from app import config
from app.database.db import get_db
from app.models.schemas import LLMSettings, RDFSettings
from app.llm.errors import LLMError
from app.llm.factory import provider_from_settings
from app.services import fuseki_service, reference_service


def get_llm_settings() -> dict:
    return config.get_llm_config(include_secret=False)


def update_llm_settings(settings: LLMSettings) -> dict:
    return config.save_llm_config(settings.model_dump())


async def test_llm_settings() -> dict:
    settings = config.get_llm_config()
    if not settings["llm_enabled"]:
        return {
            "ok": True,
            "provider": "heuristic",
            "message": "LLM désactivé : ECUME utilise l'analyse locale simple.",
            "available_models": [],
        }
    provider_name = str(settings["llm_provider"])
    models: list[str] = []
    try:
        provider = provider_from_settings(settings)
        models = await provider.list_models()
        await provider.functional_test()
        return {
            "ok": True,
            "provider": provider_name,
            "message": "Connexion OK - modèle accessible - génération OK - JSON valide",
            "available_models": models,
        }
    except (LLMError, ValueError) as exc:
        return {
            "ok": False,
            "provider": provider_name,
            "message": str(exc),
            "available_models": models,
        }


def _echo_layer_status() -> dict[str, str]:
    statuses = {"owl": "non chargé", "voc": "non chargé", "shacl": "non chargé"}
    for repository in reference_service.list_repositories():
        if not repository.get("active"):
            continue
        layers = repository.get("profile", {}).get("echo", {}).get("layers", {})
        for layer in statuses:
            if layers.get(layer, {}).get("state") not in {None, "not_provided", "insufficient"}:
                statuses[layer] = "chargé"
    settings = config.get_rdf_config()
    if settings["echo_source"] in {"fuseki", "url"}:
        for layer in statuses:
            if settings[f"echo_{layer}_reference"]:
                statuses[layer] = "configuré"
    return statuses


def get_rdf_settings() -> dict:
    return {**config.get_rdf_config(include_secret=False), "echo_layer_status": _echo_layer_status()}


def update_rdf_settings(settings: RDFSettings) -> dict:
    saved = config.save_rdf_config(settings.model_dump())
    return {**saved, "echo_layer_status": _echo_layer_status()}


async def test_rdf_settings(action: str) -> dict:
    if action == "connection":
        return await fuseki_service.health_check()
    if action in {"query", "read"}:
        rows = await fuseki_service.run_select_query("SELECT (1 AS ?value) WHERE {} LIMIT 1")
        return {
            "ok": bool(rows),
            "message": "Requête SPARQL de lecture réussie." if rows else "Fuseki est désactivé : mode local conservé.",
            "data": rows,
        }
    if action == "graphs":
        graphs = await fuseki_service.list_reference_graphs()
        return {
            "ok": bool(graphs) or fuseki_service.is_enabled(),
            "message": f"{len(graphs)} graphe(s) disponible(s)." if fuseki_service.is_enabled() else "Fuseki est désactivé.",
            "data": graphs,
        }
    if action == "write":
        return fuseki_service.write_access_status()
    raise ValueError("Test RDF inconnu.")


def check_echo_profile(check_name: str) -> dict:
    repositories = [item for item in reference_service.list_repositories() if item.get("active")]
    status = _echo_layer_status()
    checks = {
        "prefixes": any(item.get("profile", {}).get("namespaces") for item in repositories),
        "concept-scheme": status["voc"] != "non chargé",
        "shapes": status["shacl"] != "non chargé",
        "profile": status["owl"] != "non chargé" and status["voc"] != "non chargé",
    }
    if check_name not in checks:
        raise ValueError("Contrôle Echo inconnu.")
    ok = checks[check_name]
    return {
        "ok": ok,
        "message": "Contrôle local réussi." if ok else "Information insuffisante dans les référentiels locaux actifs.",
        "layers": status,
    }


async def test_ontocast() -> dict:
    settings = config.get_rdf_config()
    if not settings["ontocast_enabled"] or settings["ontocast_mode"] == "disabled":
        return {"ok": False, "message": "OntoCast n'est pas activé. Le moteur local ECUME reste disponible."}
    if settings["ontocast_mode"] == "simulation":
        return {"ok": True, "message": "Simulation OntoCast active. Aucun service externe n'est appelé."}
    if not settings["ontocast_api_url"]:
        return {"ok": False, "message": "URL OntoCast manquante. Le fallback local reste disponible."}
    try:
        headers = {}
        if settings["ontocast_api_token"]:
            headers["Authorization"] = f"Bearer {settings['ontocast_api_token']}"
        async with httpx.AsyncClient(timeout=min(settings["ontocast_timeout"], 20)) as client:
            response = await client.get(settings["ontocast_api_url"], headers=headers)
        return {"ok": response.is_success, "message": f"OntoCast a répondu avec le statut HTTP {response.status_code}."}
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"OntoCast indisponible. Le fallback local reste disponible : {exc}"}


def reset_database(*, confirmation: str, delete_uploads: bool, delete_exports: bool) -> dict:
    if confirmation != "RESET ECUME":
        raise ValueError("Confirmation invalide. Saisis exactement RESET ECUME.")
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM analysis_jobs WHERE status IN ('queued', 'running', 'cancelling')").fetchone():
            raise ValueError("Attends la fin des analyses avant de reinitialiser la base.")
    tables = [
        "review_mentions",
        "review_runs",
        "echo_mappings",
        "reference_relations",
        "reference_terms",
        "reference_repositories",
        "reference_files",
        "echo_validation_reports",
        "link_suggestions",
        "card_relations",
        "card_concepts",
        "knowledge_edges",
        "knowledge_node_aliases",
        "knowledge_nodes",
        "extracted_cards",
        "source_documents",
        "document_references",
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
