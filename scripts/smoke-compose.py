#!/usr/bin/env python3
"""Build and exercise ECUME through the frontend container reverse proxy."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]


def run(compose: list[str], *args: str, env: dict[str, str], capture: bool = False) -> str:
    result = subprocess.run(
        [*compose, *args], cwd=ROOT, env=env, check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return result.stdout or ""


def request(base: str, path: str, *, method: str = "GET", body: bytes | None = None,
            content_type: str | None = None, timeout: float = 20) -> tuple[int, bytes, str]:
    headers = {"Content-Type": content_type} if content_type else {}
    req = urllib.request.Request(f"{base}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {detail[:800]}") from exc


def json_request(base: str, path: str, *, method: str = "GET", payload=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    status, raw, _ = request(base, path, method=method, body=body,
                             content_type="application/json" if body is not None else None)
    if status != 200:
        raise RuntimeError(f"{method} {path}: HTTP {status}")
    return json.loads(raw)


def wait_http(base: str, path: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            status, _, _ = request(base, path, timeout=5)
            if status == 200:
                return
        except Exception as exc:  # service is expected to be unavailable while starting
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"Service indisponible sur {path}: {last_error}")


def upload_text(base: str) -> dict:
    boundary = f"----ecume-smoke-{uuid.uuid4().hex}"
    content = (
        "Gestion des habilitations métier\n\n"
        "Le responsable vérifie chaque demande d'accès avant de la valider. "
        "Lorsque le dossier est incomplet, la demande doit être renvoyée au demandeur. "
        "Le registre des habilitations conserve la décision et sa date pour assurer la traçabilité."
    ).encode("utf-8")
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="smoke-metier.txt"\r\n'
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
    ).encode("ascii") + content + f"\r\n--{boundary}--\r\n".encode("ascii")
    _, raw, _ = request(base, "/api/documents/upload", method="POST", body=body,
                        content_type=f"multipart/form-data; boundary={boundary}", timeout=60)
    return json.loads(raw)


def wait_job(base: str, job_id: str, timeout: float = 120) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = json_request(base, f"/api/jobs/{job_id}")
        if job["status"] in {"completed", "failed", "cancelled"}:
            if job["status"] != "completed":
                raise RuntimeError(f"Analyse {job['status']}: {job.get('error') or job.get('message')}")
            return job
        time.sleep(1)
    raise RuntimeError("L'analyse n'a pas terminé dans le délai de recette.")


def verify_frontend(base: str) -> None:
    _, index_raw, _ = request(base, "/")
    index = index_raw.decode("utf-8")
    if "/config.js" not in index:
        raise RuntimeError("Le frontend ne charge pas sa configuration runtime.")
    assets = re.findall(r'(?:src|href)="([^"]*?/assets/[^"]+\.(?:js|css))"', index)
    if not assets:
        raise RuntimeError("Le frontend servi ne référence aucun bundle Vite.")
    bundle = b"".join(request(base, asset)[1] for asset in assets)
    rendered = bundle.decode("utf-8", errors="replace")
    for label in ("Aide", "Cartes", "Exports", "Configuration LLM", "Interopérabilité RDF"):
        if label not in rendered:
            raise RuntimeError(f"Le bundle frontend ne contient pas l'écran attendu : {label}")


def exercise(base: str) -> tuple[str, str]:
    health = json_request(base, "/api/health")
    if health != {"status": "ok"}:
        raise RuntimeError(f"Santé backend inattendue : {health}")
    verify_frontend(base)

    llm = json_request(base, "/api/admin/llm")
    rdf = json_request(base, "/api/admin/rdf")
    if llm.get("llm_enabled") is not False:
        raise RuntimeError("Le smoke test attend le LLM désactivé par défaut.")
    if rdf.get("fuseki_enabled") or rdf.get("ontocast_enabled"):
        raise RuntimeError("Les services RDF optionnels doivent être désactivés par défaut.")

    document = upload_text(base)
    job = json_request(
        base,
        f"/api/documents/{document['id']}/analyze?extraction_mode=sober&fill_mode=prefilled",
        method="POST",
    )
    wait_job(base, job["id"])
    review = json_request(base, f"/api/review?document_id={document['id']}")
    if not review.get("items"):
        raise RuntimeError("L'analyse locale n'a produit aucune proposition métier.")
    mention = review["items"][0]
    mention = json_request(base, f"/api/review/{mention['id']}/decision", method="POST",
                           payload={"action": "new"})
    accepted = json_request(base, f"/api/review/{mention['id']}/decision", method="POST",
                            payload={"action": "accept"})
    if accepted.get("status") != "validated":
        raise RuntimeError("La proposition n'a pas été validée comme concept.")

    cards = json_request(base, f"/api/cards?document_id={document['id']}&status=all")
    if not cards:
        raise RuntimeError("La carte validée n'est pas consultable.")
    for path in ("/api/export/json?scope=all", "/api/export/jsonld?scope=all",
                 "/api/export/ttl?scope=all", "/api/export/csv?scope=all"):
        status, exported, _ = request(base, path, timeout=60)
        if status != 200 or not exported:
            raise RuntimeError(f"Export vide ou indisponible : {path}")

    llm["ollama_model"] = "smoke-persistence-model"
    saved = json_request(base, "/api/admin/llm", method="PUT", payload=llm)
    if saved.get("ollama_model") != "smoke-persistence-model":
        raise RuntimeError("La configuration Admin n'a pas été enregistrée.")
    return document["id"], accepted["node_id"]


def verify_persistence(base: str, document_id: str, node_id: str) -> None:
    documents = json_request(base, "/api/documents")
    graph = json_request(base, "/api/graph?scope=all")
    llm = json_request(base, "/api/admin/llm")
    if document_id not in {item["id"] for item in documents}:
        raise RuntimeError("Le document a disparu après recréation des conteneurs.")
    if node_id not in {item["id"] for item in graph["nodes"]}:
        raise RuntimeError("Le concept validé a disparu après recréation des conteneurs.")
    if llm.get("ollama_model") != "smoke-persistence-model":
        raise RuntimeError("La configuration Admin n'a pas persisté sur le volume.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Conserver les conteneurs après la recette.")
    parser.add_argument("--frontend-port", default="18080")
    parser.add_argument("--backend-port", default="18000")
    args = parser.parse_args()
    if not shutil.which("docker"):
        print("ERREUR: Docker avec Compose v2 est requis.", file=sys.stderr)
        return 2

    project = f"ecume-smoke-{os.getpid()}"
    compose = ["docker", "compose", "-p", project]
    env = dict(os.environ)
    env.update({
        "ECUME_FRONTEND_PORT": args.frontend_port,
        "ECUME_BACKEND_PORT": args.backend_port,
        "LLM_ENABLED": "false",
        "ECUME_ALLOW_LLM_FALLBACK": "false",
        "FUSEKI_ENABLED": "false",
        "ONTOCAST_ENABLED": "false",
        "ONTOSPHERE_ENABLED": "false",
        "ECUME_FUSEKI_ENABLED": "false",
        "ECUME_ONTOCAST_ENABLED": "false",
        "ECUME_ONTOSPHERE_ENABLED": "false",
    })
    base = f"http://127.0.0.1:{args.frontend_port}"
    try:
        run(compose, "config", "--quiet", env=env)
        run(compose, "up", "-d", "--build", env=env)
        wait_http(base, "/healthz", timeout=180)
        document_id, node_id = exercise(base)
        run(compose, "down", env=env)
        run(compose, "up", "-d", env=env)
        wait_http(base, "/healthz", timeout=120)
        verify_persistence(base, document_id, node_id)
        print("OK: recette Compose ECUME complète, proxy /api et persistance validés.")
        return 0
    except Exception as exc:
        print(f"ECHEC: {exc}", file=sys.stderr)
        try:
            print(run(compose, "logs", "--no-color", "--tail", "200", env=env, capture=True), file=sys.stderr)
        except Exception:
            pass
        return 1
    finally:
        if not args.keep:
            subprocess.run([*compose, "down", "-v", "--remove-orphans"], cwd=ROOT, env=env, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
