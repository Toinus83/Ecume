from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from test_mvp import isolated_data_dir
from app.database import db
from app.main import app
from app.models.schemas import MainEffect, ManualCardRequest
from app.services import analysis_service as analysis, card_service as cards
from app.services import document_service as documents, export_service as exports, graph_service as graph, job_service as jobs


CONTENT = b"Texte technique de test conserve uniquement dans le repertoire temporaire."


def upload(content=CONTENT):
    return asyncio.run(documents.save_upload(UploadFile(filename="source.txt", file=io.BytesIO(content))))


def create_card(document, label="Resultat", objects=None):
    return analysis.create_manual_card(ManualCardRequest(document_id=document["id"], theme_label="Theme",
        main_effect=MainEffect(label=label), objects=objects or [], source_excerpt="Extrait court a conserver."))


def knowledge_snapshot():
    with db.get_db() as conn:
        return {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
                for table in ("extracted_cards", "knowledge_nodes", "knowledge_edges", "link_suggestions", "knowledge_node_aliases")}


def test_default_retention_and_lightweight_document_list():
    source = upload()
    summary = documents.list_documents()[0]
    assert summary["retention_policy"] == "keep"
    assert summary["can_reanalyze"]
    assert summary["source_status"] == "retained"
    assert "content_text" not in summary
    assert len(summary["content_hash"]) == 64
    assert source["content_text"]
    documents.save_import_settings("purge_after_success")
    assert upload()["retention_policy"] == "purge_after_success"
    assert documents.get_document(source["id"])["retention_policy"] == "keep"
    db.init_db()
    assert documents.get_import_settings()["retention_policy"] == "purge_after_success"


def test_purge_preserves_all_knowledge_and_export_sources():
    source = upload()
    current = create_card(source, objects=["Objet"])
    cards.accept_card(current["id"])
    before = knowledge_snapshot()
    summary = documents.purge_source(source["id"])
    assert summary["source_status"] == "purged"
    assert not summary["can_reanalyze"]
    assert documents.get_document(source["id"])["content_text"] == ""
    assert not documents._source_path(source).exists()
    assert knowledge_snapshot() == before
    payload = json.loads(exports.export_json().read_text(encoding="utf-8"))
    assert payload["cards"][0]["source_excerpt"] == "Extrait court a conserver."
    assert payload["documents"][0]["content_hash"] == source["content_hash"]
    assert payload["nodes"][0]["source_titles"] == [source["title"]]
    linked = json.loads(exports.export_jsonld().read_text(encoding="utf-8"))
    reference = next(row for row in linked["@graph"] if row["@id"] == f"urn:ecume:document:{source['id']}")
    assert reference["sourceStatus"] == "purged"
    assert reference["contentText"] == ""
    assert documents.purge_source(source["id"])["source_status"] == "purged"


def test_restore_requires_exact_hash_and_keeps_knowledge():
    source = upload()
    create_card(source)
    documents.purge_source(source["id"])
    before = knowledge_snapshot()
    with pytest.raises(ValueError, match="empreinte"):
        documents.restore_source(source["id"], UploadFile(filename="source.txt", file=io.BytesIO(b"different")))
    assert not documents._source_path(source).exists()
    restored = documents.restore_source(source["id"], UploadFile(filename="renamed.txt", file=io.BytesIO(CONTENT)))
    assert restored["can_reanalyze"]
    assert knowledge_snapshot() == before


def test_source_purge_rolls_back_sql_and_file_on_failure(monkeypatch):
    source = upload()
    create_card(source)
    before = knowledge_snapshot()
    def fail(**kwargs):
        raise RuntimeError("journal indisponible")
    monkeypatch.setattr(documents, "record_change", fail)
    with pytest.raises(RuntimeError):
        documents.purge_source(source["id"])
    assert documents._source_path(source).read_bytes() == CONTENT
    assert documents.get_document(source["id"])["content_text"]
    assert knowledge_snapshot() == before


def test_pending_purge_is_recoverable(monkeypatch):
    source = upload()
    real_unlink = Path.unlink
    def fail_pending(path, *args, **kwargs):
        if path.suffix == ".purging":
            raise PermissionError("Fichier verrouille")
        return real_unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_pending)
        with pytest.raises(PermissionError):
            documents.purge_source(source["id"])
    assert documents.get_document(source["id"])["source_status"] == "purge_pending"
    documents.recover_pending_purges()
    assert documents.document_summary(source["id"])["source_status"] == "purged"
    assert not list(documents.UPLOAD_DIR.iterdir())


@pytest.mark.parametrize("delete_knowledge", [False, True])
def test_delete_document_preserves_shared_concepts_and_source_references(delete_knowledge):
    first, second = upload(), upload()
    a = create_card(first, label="Premier resultat", objects=["Objet commun"])
    b = create_card(second, label="Second resultat", objects=["Objet commun"])
    cards.accept_card(a["id"])
    cards.accept_card(b["id"])
    shared = a["graph_node_ids"]["objects"][0]
    before = knowledge_snapshot()
    result = documents.delete_document(first["id"], confirmation="SUPPRIMER", delete_knowledge=delete_knowledge,
                                      knowledge_confirmation="SUPPRIMER LES CONNAISSANCES")
    assert documents.get_document(first["id"]) is None
    assert graph.get_node(shared)["status"] == "accepted"
    assert analysis.get_card(b["id"])
    if delete_knowledge:
        assert analysis.get_card(a["id"]) is None
        assert result["deleted_cards"] == 1
    else:
        assert knowledge_snapshot() == before
    payload = json.loads(exports.export_json().read_text(encoding="utf-8"))
    reference = next(row for row in payload["documents"] if row["id"] == first["id"])
    assert reference["source_status"] == "deleted"
    assert reference["content_text"] == ""
    assert first["title"] in next(row for row in payload["nodes"] if row["id"] == shared)["source_titles"]


def test_delete_requires_two_explicit_confirmations():
    source = upload()
    for params in ({"confirmation": ""}, {"confirmation": "SUPPRIMER", "delete_knowledge": True}):
        with pytest.raises(ValueError):
            documents.delete_document(source["id"], **params)
        assert documents._source_path(source).exists()


def test_purged_source_cannot_be_analyzed():
    source = upload()
    documents.purge_source(source["id"])
    async def attempt():
        with pytest.raises(ValueError, match="Source indisponible"):
            jobs.start_analysis_job(source["id"])
    asyncio.run(attempt())
    assert jobs.list_jobs() == []


@pytest.mark.parametrize("success", [True, False])
def test_automatic_purge_only_after_success(monkeypatch, success):
    source = upload()
    documents.set_retention_policy(source["id"], "purge_after_success")
    async def analyze(document_id, progress_callback, *, cancel_check=None, validation_policy=None, extraction_mode="sober"):
        if not success:
            raise ValueError("LLM indisponible")
        return {"cards": [create_card(source)], "warnings": []}
    monkeypatch.setattr(analysis, "analyze_document", analyze)
    async def run():
        started = jobs.start_analysis_job(source["id"])
        duplicate = jobs.start_analysis_job(source["id"])
        assert duplicate["id"] == started["id"]
        for action in (lambda: documents.purge_source(source["id"]),
                       lambda: documents.delete_document(source["id"], confirmation="SUPPRIMER")):
            with pytest.raises(ValueError, match="en cours"):
                action()
        await asyncio.gather(*list(jobs._tasks))
        return jobs.get_job(started["id"])
    result = asyncio.run(run())
    assert result["status"] == ("completed" if success else "failed")
    assert documents.document_summary(source["id"])["source_status"] == ("purged" if success else "retained")
    if success:
        assert result["progress"] == 100
        assert analysis.get_card(result["result_card_ids"][0])


def test_recover_interrupted_job_does_not_touch_completed_or_knowledge():
    source = upload()
    create_card(source)
    before = knowledge_snapshot()
    with db.get_db() as conn:
        for status in ("running", "queued", "completed"):
            conn.execute("""INSERT INTO analysis_jobs (id, document_id, status, progress, created_at, updated_at)
                VALUES (?, ?, ?, 10, ?, ?)""", (status, source["id"], status, db.now_iso(), db.now_iso()))
    jobs.recover_interrupted_jobs()
    assert jobs.get_job("running")["status"] == "failed"
    assert jobs.get_job("queued")["finished_at"]
    assert jobs.get_job("completed")["status"] == "completed"
    assert knowledge_snapshot() == before


def test_document_counts_deduplicate_shared_concepts():
    source = upload()
    a = create_card(source, "Resultat A", ["Partage"])
    b = create_card(source, "Resultat B", ["Partage"])
    cards.accept_card(a["id"])
    cards.accept_card(b["id"])
    summary = documents.document_summary(source["id"])
    assert summary["card_count"] == 2
    assert summary["concept_counts"]["validated"] == 4  # two effects, one theme, one shared object


def test_api_lifecycle_and_repeated_migration():
    with TestClient(app) as client:
        source = client.post("/documents/upload", files={"file": ("source.txt", CONTENT)}).json()
        assert client.get("/imports/settings").json()["retention_policy"] == "keep"
        assert client.put("/imports/settings", json={"retention_policy": "invalid"}).status_code == 422
        assert client.post(f"/documents/{source['id']}/purge").status_code == 200
        assert client.post(f"/documents/{source['id']}/analyze").status_code == 400
        assert client.post(f"/documents/{source['id']}/source", files={"file": ("source.txt", CONTENT)}).status_code == 200
        db.init_db()
        db.init_db()
        assert client.get("/documents").json()[0]["can_reanalyze"]


def test_restart_recovers_source_staged_before_sql_commit():
    source = upload()
    path = documents._source_path(source)
    path.rename(documents._pending_path(path))
    documents.recover_pending_purges()
    assert path.read_bytes() == CONTENT
    assert documents.document_summary(source["id"])["can_reanalyze"]


def test_restore_rolls_back_file_if_transaction_fails(monkeypatch):
    from contextlib import contextmanager
    source = upload()
    documents.purge_source(source["id"])
    real_transaction = documents.transaction
    @contextmanager
    def failing_transaction():
        with real_transaction() as conn:
            yield conn
            raise RuntimeError("Echec avant commit")
    with monkeypatch.context() as patch:
        patch.setattr(documents, "transaction", failing_transaction)
        with pytest.raises(RuntimeError):
            documents.restore_source(source["id"], UploadFile(filename="source.txt", file=io.BytesIO(CONTENT)))
    assert documents.get_document(source["id"])["source_status"] == "purged"
    assert not documents._source_path(source).exists()


def test_delete_knowledge_rolls_back_on_failure(monkeypatch):
    source = upload()
    create_card(source)
    before = knowledge_snapshot()
    original = cards.delete_card
    def fail_after_delete(card_id):
        original(card_id)
        raise RuntimeError("Echec de suppression")
    monkeypatch.setattr(cards, "delete_card", fail_after_delete)
    with pytest.raises(RuntimeError):
        documents.delete_document(source["id"], confirmation="SUPPRIMER", delete_knowledge=True,
                                  knowledge_confirmation="SUPPRIMER LES CONNAISSANCES")
    assert knowledge_snapshot() == before
    assert documents.get_document(source["id"])["source_status"] == "purged"
