from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import uuid

from fastapi import UploadFile

from app.config import UPLOAD_DIR
from app.database.db import get_db, now_iso, transaction
from app.services.changelog_service import record_change
from app.services.serialization import row_to_dict, rows_to_dicts


SUPPORTED_TEXT_TYPES = {".txt", ".md"}
_ACTIVE_IMPORTS: set[str] = set()
_CANCELLED_IMPORTS: set[str] = set()
DOMAIN_KEYWORDS = {
    "RH": ("ressources humaines", "recrutement", "emploi", "personnel", "formation", "compétence", "carrière"),
    "METEO": ("météo", "meteorologie", "prévision", "vent", "température", "pression", "précipitation"),
    "OPERATIONS": ("opération", "mission", "doctrine", "engagement", "commandement", "situation tactique"),
    "LOGISTIQUE": ("logistique", "approvisionnement", "stock", "transport", "maintenance", "ravitaillement"),
    "C2": ("commandement et contrôle", "c2", "coordination", "chaîne de commandement", "conduite des opérations"),
    "URBANISME": ("urbanisme", "permis de construire", "plu", "zone urbaine", "aménagement", "construction"),
}


def request_import_cancel(upload_id: str) -> dict:
    if not upload_id:
        raise ValueError("Import introuvable.")
    _CANCELLED_IMPORTS.add(upload_id)
    return {"status": "cancelling" if upload_id in _ACTIVE_IMPORTS else "cancel_requested"}


def _cancelled(upload_id: str) -> bool:
    return bool(upload_id and upload_id in _CANCELLED_IMPORTS)


def _check_import(upload_id: str) -> None:
    if _cancelled(upload_id):
        raise ValueError("Import arrêté à la demande de l’utilisateur.")


def _extract_text(path: Path, extension: str, upload_id: str = "") -> str:
    _check_import(upload_id)
    if extension in SUPPORTED_TEXT_TYPES:
        return path.read_text(encoding="utf-8", errors="replace")
    if extension == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages:
                _check_import(upload_id)
                pages.append(page.extract_text() or "")
            return "\n".join(pages)
        except Exception as exc:
            raise ValueError(f"Impossible d'extraire le texte du PDF : {exc}") from exc
    if extension == ".docx":
        try:
            from docx import Document

            doc = Document(str(path))
            paragraphs = []
            for paragraph in doc.paragraphs:
                _check_import(upload_id)
                paragraphs.append(paragraph.text)
            return "\n".join(paragraphs)
        except Exception as exc:
            raise ValueError(f"Impossible d'extraire le texte du DOCX : {exc}") from exc
    raise ValueError("Format non supporté pour le MVP. Utilise .txt, .md, .pdf ou .docx.")


async def save_upload(file: UploadFile, upload_id: str = "") -> dict:
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(_save_upload, file, upload_id)


def _save_upload(file: UploadFile, upload_id: str = "") -> dict:
    if not file.filename:
        raise ValueError("Nom de fichier absent.")
    extension = Path(file.filename).suffix.lower()
    if extension not in {".txt", ".md", ".pdf", ".docx"}:
        raise ValueError("Format non supporté pour le MVP. Utilise .txt, .md, .pdf ou .docx.")

    upload_id = upload_id or str(uuid.uuid4())
    _ACTIVE_IMPORTS.add(upload_id)
    document_id = str(uuid.uuid4())
    stored_name = f"{document_id}{extension}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_DIR / stored_name
    try:
        with stored_path.open("wb") as buffer:
            while True:
                _check_import(upload_id)
                block = file.file.read(1024 * 1024)
                if not block:
                    break
                buffer.write(block)
        _check_import(upload_id)
        content_text = _extract_text(stored_path, extension, upload_id).strip()
        if not content_text:
            raise ValueError("Aucun texte exploitable n'a été extrait du document.")
        digest = _file_hash(stored_path)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    finally:
        _ACTIVE_IMPORTS.discard(upload_id)
        _CANCELLED_IMPORTS.discard(upload_id)

    title = Path(file.filename).stem.replace("_", " ").replace("-", " ").strip() or file.filename
    created_at = now_iso()
    try:
        with transaction() as conn:
            conn.execute(
                """INSERT INTO source_documents
                (id, title, filename, file_type, content_text, created_at, metadata,
                 content_hash, content_length, retention_policy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (document_id, title, file.filename, extension.lstrip("."), content_text, created_at, "{}",
                 digest, len(content_text), get_import_settings()["retention_policy"]),
            )
            row = conn.execute("SELECT * FROM source_documents WHERE id = ?", (document_id,)).fetchone()
    except BaseException:
        stored_path.unlink(missing_ok=True)
        raise
    return row_to_dict(row)


def list_documents() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM source_documents ORDER BY created_at DESC"
        ).fetchall()
    return [document_summary(row["id"]) for row in rows]


def get_document(document_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM source_documents WHERE id = ?", (document_id,)
        ).fetchone()
    return row_to_dict(row) if row else None


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_path(document: dict) -> Path:
    # Never trust an original filename or a path stored in metadata for deletion.
    if str(uuid.UUID(document["id"])) != document["id"]:
        raise ValueError("Identifiant documentaire invalide.")
    if document["file_type"] not in {"txt", "md", "pdf", "docx", "manual"}:
        raise ValueError("Ce document n'a pas de fichier source gere par ECUME.")
    root = UPLOAD_DIR.resolve()
    path = root / f"{document['id']}.{document['file_type']}"
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError("Chemin source non autorise.")
    return path


def _pending_path(path: Path) -> Path:
    pending = path.with_name(path.name + ".purging")
    if pending.is_symlink() or pending.resolve().parent != path.parent:
        raise ValueError("Chemin de purge non autorise.")
    return pending


def get_import_settings() -> dict:
    with get_db() as conn:
        return dict(conn.execute("SELECT retention_policy FROM import_settings WHERE id = 1").fetchone())


def save_import_settings(policy: str) -> dict:
    _check_policy(policy)
    with transaction() as conn:
        conn.execute("UPDATE import_settings SET retention_policy = ? WHERE id = 1", (policy,))
        record_change(entity_type="settings", entity_id="imports", action="retention_changed",
                      origin="user", details={"retention_policy": policy})
    return get_import_settings()


def _check_policy(policy: str) -> None:
    if policy not in {"keep", "purge_after_success"}:
        raise ValueError("Politique de conservation invalide.")


def _require_document(document_id: str) -> dict:
    document = get_document(document_id)
    if not document:
        raise ValueError("Document introuvable.")
    return document


def assert_document_idle(document_id: str) -> None:
    with get_db() as conn:
        active = conn.execute("SELECT 1 FROM analysis_jobs WHERE document_id = ? AND status IN ('queued', 'running', 'cancelling')",
                              (document_id,)).fetchone()
    if active:
        raise ValueError("Une analyse est en cours pour ce document. Attends sa fin.")


def set_retention_policy(document_id: str, policy: str) -> dict:
    _check_policy(policy)
    with transaction() as conn:
        _require_document(document_id)
        assert_document_idle(document_id)
        conn.execute("UPDATE source_documents SET retention_policy = ? WHERE id = ?", (policy, document_id))
        record_change(entity_type="document", entity_id=document_id, action="retention_changed",
                      origin="user", source_id=document_id, details={"retention_policy": policy})
    return document_summary(document_id)


def propose_domain(document_id: str) -> dict:
    from app.services.graph_service import _normalize
    document = _require_document(document_id)
    text = _normalize(document.get("content_text", ""))
    evidence = []
    with get_db() as conn:
        repositories = conn.execute("SELECT id,name FROM reference_repositories WHERE active=1").fetchall()
        for repository in repositories:
            matches = []
            for term in conn.execute("SELECT label,aliases FROM reference_terms WHERE repository_id=?", (repository["id"],)):
                labels = [term["label"], *json.loads(term["aliases"] or "[]")]
                found = next((label for label in labels if len(_normalize(label)) >= 3 and _normalize(label) in text), "")
                if found:
                    matches.append(found)
                if len(matches) >= 12:
                    break
            if matches:
                evidence.append({"domain": repository["name"], "source": "référentiel reconnu",
                                 "terms": matches[:5], "score": min(0.95, 0.55 + len(matches) * 0.04)})
    for domain, keywords in DOMAIN_KEYWORDS.items():
        matches = [keyword for keyword in keywords if _normalize(keyword) in text]
        if matches:
            evidence.append({"domain": domain, "source": "mots-clés du document",
                             "terms": matches[:5], "score": min(0.85, 0.45 + len(matches) * 0.08)})
    evidence.sort(key=lambda item: (-item["score"], item["domain"].casefold()))
    proposed = evidence[0]["domain"] if evidence else "Domaine à préciser"
    with transaction() as conn:
        current = conn.execute("SELECT domain_status FROM source_documents WHERE id=?", (document_id,)).fetchone()
        if current and current["domain_status"] != "confirmed":
            conn.execute("UPDATE source_documents SET proposed_domain=?, domain_evidence=? WHERE id=?",
                         (proposed, json.dumps(evidence, ensure_ascii=False), document_id))
            record_change(entity_type="document", entity_id=document_id, action="domain_proposed",
                          origin="analysis", source_id=document_id,
                          details={"proposed_domain": proposed, "evidence": evidence})
    return document_summary(document_id)


def confirm_domain(document_id: str, confirmed_domain: str, secondary_domains: list[str],
                   no_suitable_reference: bool = False) -> dict:
    document = _require_document(document_id)
    domain = confirmed_domain.strip()[:160]
    secondary = list(dict.fromkeys(value.strip()[:160] for value in secondary_domains if value.strip()))[:8]
    if not domain and not no_suitable_reference:
        raise ValueError("Choisis un domaine ou indique qu'aucun référentiel n'est adapté.")
    if no_suitable_reference and not domain:
        domain = document.get("proposed_domain") or "Domaine métier sans référentiel"
    with transaction() as conn:
        conn.execute("""UPDATE source_documents SET confirmed_domain=?, secondary_domains=?,
            domain_status=? WHERE id=?""", (domain, json.dumps(secondary, ensure_ascii=False),
            "no_reference" if no_suitable_reference else "confirmed", document_id))
        record_change(entity_type="document", entity_id=document_id, action="domain_confirmed",
                      origin="user", source_id=document_id,
                      details={"confirmed_domain": domain, "secondary_domains": secondary,
                               "no_suitable_reference": no_suitable_reference})
    return document_summary(document_id)


def document_summary(document_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute("""SELECT id, title, filename, file_type, created_at, metadata,
            source_status, retention_policy, content_hash, content_length, source_purged_at,
            proposed_domain, confirmed_domain, secondary_domains, domain_status, domain_evidence,
            length(content_text) AS text_length FROM source_documents WHERE id = ?""", (document_id,)).fetchone()
    if not row:
        raise ValueError("Document introuvable.")
    document = row_to_dict(row)
    text_length = document.pop("text_length")
    document["content_length"] = document["content_length"] or text_length
    try:
        available = document["source_status"] == "retained" and _source_path(document).is_file()
    except ValueError:
        available = False
    document["source_available"] = available
    document["can_reanalyze"] = available and text_length > 0
    if not available and document["source_status"] == "retained":
        document["source_status"] = "missing"
    with get_db() as conn:
        latest = conn.execute("SELECT * FROM analysis_jobs WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
                              (document_id,)).fetchone()
        active = conn.execute("SELECT * FROM analysis_jobs WHERE document_id = ? AND status IN ('queued', 'running', 'cancelling') ORDER BY created_at DESC LIMIT 1",
                              (document_id,)).fetchone()
        document["latest_job"] = row_to_dict(active or latest) if active or latest else None
        document["card_count"] = conn.execute("SELECT COUNT(*) FROM extracted_cards WHERE document_id = ?", (document_id,)).fetchone()[0]
        cards = conn.execute("SELECT status, business_validation_status FROM extracted_cards WHERE document_id = ?", (document_id,)).fetchall()
        nodes = conn.execute("""SELECT DISTINCT n.id, n.status, n.business_validation_status, n.orphan_status
            FROM knowledge_nodes n WHERE n.id IN (
                SELECT b.node_id FROM card_concepts b JOIN extracted_cards c ON c.id = b.card_id WHERE c.document_id = ?)
            OR EXISTS (SELECT 1 FROM json_each(n.source_ids) WHERE value = ?)""", (document_id, document_id)).fetchall()
    from app.services.coherence_service import is_valid
    counts = {"validated": 0, "auto_validated": 0, "to_review": 0, "rejected": 0, "pending": 0}
    for row in nodes:
        node = dict(row)
        key = "auto_validated" if is_valid(node) and node["business_validation_status"] == "auto_validated" else \
              "validated" if is_valid(node) else "rejected" if node["status"] == "rejected" else \
              "to_review" if node["status"] == "to_confirm" or node["business_validation_status"] == "to_review" or node["orphan_status"] == "orphan_to_review" else "pending"
        counts[key] += 1
    document["concept_counts"] = counts
    card_counts = {"validated": 0, "auto_validated": 0, "to_review": 0, "rejected": 0, "pending": 0, "linked": 0}
    for row in cards:
        card = dict(row)
        key = "auto_validated" if is_valid(card) and card["business_validation_status"] == "auto_validated" else \
              "validated" if is_valid(card) else "rejected" if card["status"] == "rejected" else \
              "linked" if card["status"] == "linked" else "to_review" if card["status"] == "to_confirm" else "pending"
        card_counts[key] += 1
    document["card_counts"] = card_counts
    return document


def purge_source(document_id: str, *, origin: str = "user") -> dict:
    staged = None
    moved = False
    try:
        with transaction() as conn:
            document = _require_document(document_id)
            assert_document_idle(document_id)
            path = _source_path(document)
            staged = _pending_path(path)
            digest = document["content_hash"]
            if path.exists():
                if staged.exists():
                    raise ValueError("Une purge precedente doit etre terminee avant cette action.")
                digest = digest or _file_hash(path)
                path.rename(staged)
                moved = True
            conn.execute("""UPDATE source_documents SET content_text = '', source_status = 'purge_pending',
                content_hash = ?, content_length = ?, source_purged_at = ? WHERE id = ?""",
                (digest, document["content_length"] or len(document["content_text"]), now_iso(), document_id))
            record_change(entity_type="document", entity_id=document_id, action="source_purge_requested",
                          origin=origin, source_id=document_id, details={"knowledge_preserved": True})
    except BaseException:
        if moved and staged and staged.exists():
            staged.rename(path)
        raise
    # File deletion follows the SQL commit. A crash leaves a recoverable pending purge.
    finish_pending_purge(document_id)
    return document_summary(document_id)


def finish_pending_purge(document_id: str) -> None:
    with transaction() as conn:
        document = _require_document(document_id)
        if document["source_status"] != "purge_pending":
            return
        assert_document_idle(document_id)
        path = _source_path(document)
        staged = _pending_path(path)
        if path.exists():
            raise ValueError("Un fichier source est present pendant la purge ; suppression refusee.")
        staged.unlink(missing_ok=True)
        conn.execute("UPDATE source_documents SET source_status = 'purged' WHERE id = ?", (document_id,))
        record_change(entity_type="document", entity_id=document_id, action="source_purged",
                      origin="purge", source_id=document_id, details={"knowledge_preserved": True})


def recover_pending_purges() -> None:
    import logging
    with get_db() as conn:
        documents = [dict(row) for row in conn.execute("SELECT id, file_type, source_status FROM source_documents")]
    for document in documents:
        try:
            if document["source_status"] == "purge_pending":
                finish_pending_purge(document["id"])
            elif document["source_status"] == "retained":
                path = _source_path(document)
                staged = _pending_path(path)
                if staged.exists() and not path.exists():
                    staged.rename(path)
        except (OSError, ValueError):
            logging.getLogger(__name__).exception("Purge en attente pour %s", document["id"])


def restore_source(document_id: str, file: UploadFile) -> dict:
    created_paths: list[Path] = []
    try:
        _restore_source(document_id, file, created_paths.append)
    except BaseException:
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise
    return document_summary(document_id)


def _restore_source(document_id: str, file: UploadFile, mark_created) -> None:
    with transaction() as conn:
        document = _require_document(document_id)
        assert_document_idle(document_id)
        path = _source_path(document)
        if document["source_status"] == "purge_pending":
            raise ValueError("Termine la purge en attente avant de fournir le fichier.")
        if path.exists():
            raise ValueError("La source est deja disponible.")
        if Path(file.filename or "").suffix.lower() != path.suffix:
            raise ValueError("Le format ne correspond pas au document d'origine.")
        # A legacy source with no fingerprint cannot be matched safely by name alone.
        if not document["content_hash"]:
            raise ValueError("Empreinte d'origine absente : importe ce fichier comme nouveau document.")
        with path.open("xb") as output:
            mark_created(path)
            shutil.copyfileobj(file.file, output)
        if _file_hash(path) != document["content_hash"]:
            raise ValueError("Ce fichier ne correspond pas a l'empreinte du document d'origine.")
        content = _extract_text(path, path.suffix).strip()
        if not content:
            raise ValueError("Aucun texte exploitable.")
        conn.execute("UPDATE source_documents SET content_text = ?, source_status = 'retained', source_purged_at = NULL WHERE id = ?",
                     (content, document_id))
        record_change(entity_type="document", entity_id=document_id, action="source_restored",
                      origin="user", source_id=document_id, details={"hash_verified": True})


def delete_document(document_id: str, *, confirmation: str, delete_knowledge: bool = False,
                    knowledge_confirmation: str = "") -> dict:
    if confirmation != "SUPPRIMER":
        raise ValueError("Saisis SUPPRIMER pour confirmer.")
    if delete_knowledge and knowledge_confirmation != "SUPPRIMER LES CONNAISSANCES":
        raise ValueError("Confirme explicitement : SUPPRIMER LES CONNAISSANCES.")
    # Purge is independently durable: a later SQL failure never loses knowledge.
    purge_source(document_id)
    from app.services import card_service, coherence_service, graph_service
    with transaction() as conn:
        document = _require_document(document_id)
        assert_document_idle(document_id)
        deleted_cards, deleted_nodes = [], []
        if delete_knowledge:
            conn.execute("DELETE FROM review_mentions WHERE document_id = ?", (document_id,))
            conn.execute("DELETE FROM review_runs WHERE document_id = ?", (document_id,))
            candidates = [node for node in graph_service.list_nodes()
                          if document_id in node["source_ids"] and set(node["source_ids"]) == {document_id}]
            card_ids = [row[0] for row in conn.execute("SELECT id FROM extracted_cards WHERE document_id = ?", (document_id,))]
            for card_id in card_ids:
                card_service.delete_card(card_id)
                deleted_cards.append(card_id)
            for node in candidates:
                if conn.execute("SELECT 1 FROM review_mentions WHERE node_id=? AND document_id<>? AND status IN ('known','validated')", (node['id'],document_id)).fetchone():
                    continue
                if coherence_service.concept_users(node["id"]):
                    continue
                incident = [edge for edge in graph_service.list_edges() if node["id"] in (edge["source_node_id"], edge["target_node_id"])]
                if any(set(edge["source_ids"]) - {document_id} for edge in incident):
                    continue
                graph_service.delete_node(node["id"])
                deleted_nodes.append(node["id"])
        conn.execute("""INSERT INTO document_references
            (id, title, filename, file_type, created_at, content_hash, content_length, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (
                document_id, document["title"], document["filename"], document["file_type"], document["created_at"],
                document["content_hash"], document["content_length"], now_iso()))
        conn.execute("DELETE FROM analysis_jobs WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM source_documents WHERE id = ?", (document_id,))
        record_change(entity_type="document", entity_id=document_id, action="document_deleted", origin="user",
                      source_id=document_id, details={"title": document["title"], "deleted_card_ids": deleted_cards,
                      "deleted_node_ids": deleted_nodes, "knowledge_preserved": not delete_knowledge})
    return {"deleted_document_id": document_id, "deleted_cards": len(deleted_cards), "deleted_nodes": len(deleted_nodes)}
