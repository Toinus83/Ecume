from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import httpx

from app import config


SELECT_LIMIT = 100


def is_enabled() -> bool:
    return bool(config.get_rdf_config()["fuseki_enabled"])


def _settings() -> dict[str, Any]:
    return config.get_rdf_config()


def _endpoint_url(settings: dict[str, Any], endpoint: str) -> str:
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    base = str(settings["fuseki_base_url"]).rstrip("/")
    dataset = str(settings["fuseki_dataset"]).strip("/")
    suffix = endpoint if endpoint.startswith("/") else f"/{endpoint}"
    return f"{base}/{dataset}{suffix}"


def _request_options(settings: dict[str, Any]) -> dict[str, Any]:
    headers = {"Accept": "application/sparql-results+json"}
    auth = None
    if settings["rdf_auth_type"] == "basic":
        auth = httpx.BasicAuth(settings["rdf_auth_username"], settings["rdf_auth_secret"])
    elif settings["rdf_auth_type"] == "bearer" and settings["rdf_auth_secret"]:
        headers["Authorization"] = f"Bearer {settings['rdf_auth_secret']}"
    return {"headers": headers, "auth": auth}


async def health_check() -> dict[str, Any]:
    if not is_enabled():
        return {"ok": False, "enabled": False, "message": "Fuseki n'est pas activé. ECUME reste en mode local."}
    try:
        rows = await run_select_query("SELECT (1 AS ?value) WHERE {} LIMIT 1")
        return {
            "ok": bool(rows),
            "enabled": True,
            "message": "Connexion Fuseki opérationnelle." if rows else "Fuseki répond, sans résultat de contrôle.",
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "enabled": True, "message": f"Fuseki indisponible : {exc}"}


async def run_select_query(query: str) -> list[dict[str, str]]:
    if not is_enabled():
        return []
    normalized = query.lstrip().upper()
    if not normalized.startswith(("SELECT", "ASK")):
        raise ValueError("Seules les requêtes SPARQL de lecture SELECT ou ASK sont autorisées.")
    settings = _settings()
    options = _request_options(settings)
    timeout = httpx.Timeout(20, connect=5)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            _endpoint_url(settings, settings["fuseki_query_endpoint"]),
            data={"query": query},
            **options,
        )
        response.raise_for_status()
    payload = response.json()
    if "boolean" in payload:
        return [{"boolean": str(bool(payload["boolean"])).lower()}]
    rows: list[dict[str, str]] = []
    for binding in payload.get("results", {}).get("bindings", [])[:SELECT_LIMIT]:
        rows.append({key: str(value.get("value", "")) for key, value in binding.items()})
    return rows


async def list_reference_graphs() -> list[str]:
    rows = await run_select_query("SELECT DISTINCT ?graph WHERE { GRAPH ?graph { ?s ?p ?o } } ORDER BY ?graph")
    return [row["graph"] for row in rows if row.get("graph")]


def _sparql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")


async def find_close_concepts(label: str, domain: str | None = None) -> list[dict[str, Any]]:
    if not is_enabled() or not label.strip():
        return []
    settings = _settings()
    graphs = [settings["graph_echo_owl"], settings["graph_echo_voc"], settings["graph_echo_shacl"]]
    graph_values = " ".join(f"<{graph}>" for graph in graphs if graph)
    needle = _sparql_literal(label.strip().casefold())
    query = f"""
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?uri ?label ?alt ?graph WHERE {{
  VALUES ?graph {{ {graph_values} }}
  GRAPH ?graph {{
    ?uri (skos:prefLabel|rdfs:label) ?label .
    OPTIONAL {{ ?uri skos:altLabel ?alt }}
    FILTER(CONTAINS(LCASE(STR(?label)), "{needle}") || CONTAINS(LCASE(STR(?alt)), "{needle}"))
  }}
}} LIMIT 30
"""
    rows = await run_select_query(query)
    candidates: dict[str, dict[str, Any]] = {}
    normalized = label.strip().casefold()
    for row in rows:
        canonical = row.get("label", "").strip()
        alias = row.get("alt", "").strip()
        if canonical.casefold() == normalized:
            match_type, score, reason = "exactLabel", 1.0, "Libellé exact dans le référentiel Echo."
        elif alias and alias.casefold() == normalized:
            match_type, score, reason = "altLabel", 0.94, "Synonyme exact dans le vocabulaire Echo."
        else:
            similarity = max(
                SequenceMatcher(None, normalized, canonical.casefold()).ratio(),
                SequenceMatcher(None, normalized, alias.casefold()).ratio() if alias else 0,
            )
            match_type, score, reason = "lexical", round(max(0.5, similarity), 2), "Libellé lexicalement proche."
        candidate = {
            "uri": row.get("uri", ""),
            "label": canonical,
            "source_graph": row.get("graph", ""),
            "source": "Echo via Fuseki",
            "match_type": match_type,
            "score": score,
            "reason": reason,
            "domain": domain or settings["echo_default_domain"],
        }
        current = candidates.get(candidate["uri"])
        if candidate["uri"] and (not current or score > current["score"]):
            candidates[candidate["uri"]] = candidate
    return sorted(candidates.values(), key=lambda item: (-item["score"], item["label"].casefold()))


def write_access_status() -> dict[str, Any]:
    settings = _settings()
    if not settings["fuseki_enabled"]:
        return {"ok": False, "message": "Fuseki est désactivé. Aucune écriture externe n'est réalisée."}
    if settings["fuseki_write_mode"] == "disabled" or settings["rdf_read_only"]:
        return {"ok": False, "message": "Écriture désactivée : ECUME fonctionne en lecture seule."}
    return {
        "ok": True,
        "message": "Configuration d'écriture cohérente. Aucun SPARQL Update n'a été exécuté par ce test préparatoire.",
    }
