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


def _extract_text(path: Path, extension: str) -> str:
    if extension in SUPPORTED_TEXT_TYPES:
        return path.read_text(encoding="utf-8", errors="replace")
    if extension == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError(f"Impossible d'extraire le texte du PDF : {exc}") from exc
    if extension == ".docx":
        try:
            from docx import Document

            doc = Document(str(path))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        except Exception as exc:
            raise ValueError(f"Impossible d'extraire le texte du DOCX : {exc}") from exc
    raise ValueError("Format non supporté pour le MVP. Utilise .txt, .md, .pdf ou .docx.")


async def save_upload(file: UploadFile) -> dict:
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(_save_upload, file)


def _save_upload(file: UploadFile) -> dict:
    if not file.filename:
        raise ValueError("Nom de fichier absent.")
    extension = Path(file.filename).suffix.lower()
    if extension not in {".txt", ".md", ".pdf", ".docx"}:
        raise ValueError("Format non supporté pour le MVP. Utilise .txt, .md, .pdf ou .docx.")

    document_id = str(uuid.uuid4())
    stored_name = f"{document_id}{extension}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_DIR / stored_name
    try:
        with stored_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        content_text = _extract_text(stored_path, extension).strip()
        if not content_text:
            raise ValueError("Aucun texte exploitable n'a été extrait du document.")
        digest = _file_hash(stored_path)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise

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
        active = conn.execute("SELECT 1 FROM analysis_jobs WHERE document_id = ? AND status IN ('queued', 'running')",
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


def document_summary(document_id: str) -> dict:
    with get_db() as conn:
        row = conn.execute("""SELECT id, title, filename, file_type, created_at, metadata,
            source_status, retention_policy, content_hash, content_length, source_purged_at,
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
        active = conn.execute("SELECT * FROM analysis_jobs WHERE document_id = ? AND status IN ('queued', 'running') ORDER BY created_at DESC LIMIT 1",
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
            candidates = [node for node in graph_service.list_nodes()
                          if document_id in node["source_ids"] and set(node["source_ids"]) == {document_id}]
            card_ids = [row[0] for row in conn.execute("SELECT id FROM extracted_cards WHERE document_id = ?", (document_id,))]
            for card_id in card_ids:
                card_service.delete_card(card_id)
                deleted_cards.append(card_id)
            for node in candidates:
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
