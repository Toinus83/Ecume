from __future__ import annotations

from pathlib import Path
import shutil
import uuid

from fastapi import UploadFile

from app.config import UPLOAD_DIR
from app.database.db import get_db, now_iso
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
    if not file.filename:
        raise ValueError("Nom de fichier absent.")
    extension = Path(file.filename).suffix.lower()
    if extension not in {".txt", ".md", ".pdf", ".docx"}:
        raise ValueError("Format non supporté pour le MVP. Utilise .txt, .md, .pdf ou .docx.")

    document_id = str(uuid.uuid4())
    stored_name = f"{document_id}{extension}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_DIR / stored_name
    with stored_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    content_text = _extract_text(stored_path, extension).strip()
    if not content_text:
        raise ValueError("Aucun texte exploitable n'a été extrait du document.")

    title = Path(file.filename).stem.replace("_", " ").replace("-", " ").strip() or file.filename
    created_at = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO source_documents
            (id, title, filename, file_type, content_text, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, title, file.filename, extension.lstrip("."), content_text, created_at, "{}"),
        )
        row = conn.execute("SELECT * FROM source_documents WHERE id = ?", (document_id,)).fetchone()
    return row_to_dict(row)


def list_documents() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM source_documents ORDER BY created_at DESC"
        ).fetchall()
    return rows_to_dicts(rows)


def get_document(document_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM source_documents WHERE id = ?", (document_id,)
        ).fetchone()
    return row_to_dict(row) if row else None
