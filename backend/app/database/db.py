from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from datetime import datetime, timezone
import sqlite3
from typing import Iterator

from app.config import DATA_DIR, DB_PATH, EXPORT_DIR, UPLOAD_DIR

_transaction_connection: ContextVar[sqlite3.Connection | None] = ContextVar("ecume_transaction", default=None)


@contextmanager
def transaction():
    existing = _transaction_connection.get()
    if existing is not None:
        yield existing
        return
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        token = _transaction_connection.set(conn)
        try:
            yield conn
        finally:
            _transaction_connection.reset(token)


def atomic(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with transaction():
            return function(*args, **kwargs)
    return wrapped


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    existing = _transaction_connection.get()
    if existing is not None:
        yield existing
        return
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    ensure_data_dirs()
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                content_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS extracted_cards (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                theme_label TEXT NOT NULL,
                main_effect TEXT NOT NULL,
                level TEXT NOT NULL,
                objects TEXT NOT NULL DEFAULT '[]',
                actions TEXT NOT NULL DEFAULT '[]',
                conditions TEXT NOT NULL DEFAULT '[]',
                tasks TEXT NOT NULL DEFAULT '[]',
                secondary_effects TEXT NOT NULL DEFAULT '[]',
                suggested_links TEXT NOT NULL DEFAULT '[]',
                confidence TEXT NOT NULL,
                status TEXT NOT NULL,
                validation_status TEXT NOT NULL DEFAULT 'proposed',
                source_excerpt TEXT NOT NULL DEFAULT '',
                warnings TEXT NOT NULL DEFAULT '[]',
                graph_node_ids TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES source_documents(id)
            );

            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                level TEXT NOT NULL DEFAULT 'unknown',
                status TEXT NOT NULL DEFAULT 'proposed',
                validation_status TEXT NOT NULL DEFAULT 'proposed',
                confidence TEXT NOT NULL DEFAULT 'medium',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_ids TEXT NOT NULL DEFAULT '[]',
                metadata TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS knowledge_edges (
                id TEXT PRIMARY KEY,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                label TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed',
                confidence TEXT NOT NULL DEFAULT 'medium',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source_ids TEXT NOT NULL DEFAULT '[]',
                metadata TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(source_node_id) REFERENCES knowledge_nodes(id),
                FOREIGN KEY(target_node_id) REFERENCES knowledge_nodes(id)
            );

            CREATE TABLE IF NOT EXISTS knowledge_node_aliases (
                id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                label TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'variant',
                created_at TEXT NOT NULL,
                source_id TEXT,
                FOREIGN KEY(node_id) REFERENCES knowledge_nodes(id)
            );

            CREATE TABLE IF NOT EXISTS change_log (
                id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                origin TEXT NOT NULL,
                source_id TEXT,
                created_at TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS analysis_jobs (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                step TEXT NOT NULL DEFAULT 'queued',
                message TEXT NOT NULL DEFAULT '',
                current_chunk INTEGER NOT NULL DEFAULT 0,
                total_chunks INTEGER NOT NULL DEFAULT 0,
                result_card_ids TEXT NOT NULL DEFAULT '[]',
                warnings TEXT NOT NULL DEFAULT '[]',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                FOREIGN KEY(document_id) REFERENCES source_documents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_cards_document ON extracted_cards(document_id);
            CREATE TABLE IF NOT EXISTS reference_repositories (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, filename TEXT NOT NULL,
                format TEXT NOT NULL, content_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                namespace TEXT NOT NULL DEFAULT '', version TEXT NOT NULL DEFAULT '',
                profile TEXT NOT NULL DEFAULT '{}', source_content BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reference_terms (
                id TEXT PRIMARY KEY, repository_id TEXT NOT NULL, uri TEXT NOT NULL,
                label TEXT NOT NULL, aliases TEXT NOT NULL DEFAULT '[]',
                definition TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '', types TEXT NOT NULL DEFAULT '[]',
                properties TEXT NOT NULL DEFAULT '{}', UNIQUE(repository_id, uri)
            );
            CREATE TABLE IF NOT EXISTS reference_relations (
                repository_id TEXT NOT NULL, source_uri TEXT NOT NULL, target_uri TEXT NOT NULL,
                relation_type TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(repository_id, source_uri, target_uri, relation_type)
            );
            CREATE TABLE IF NOT EXISTS echo_mappings (
                id TEXT PRIMARY KEY, node_id TEXT NOT NULL, repository_id TEXT NOT NULL,
                target_uri TEXT NOT NULL, match_type TEXT NOT NULL, score REAL NOT NULL,
                reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate',
                decision_origin TEXT NOT NULL DEFAULT 'heuristic', node_signature TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(node_id, repository_id, target_uri)
            );
            CREATE INDEX IF NOT EXISTS idx_reference_terms_repo ON reference_terms(repository_id);
            CREATE TABLE IF NOT EXISTS reference_files (
                id TEXT PRIMARY KEY, repository_id TEXT NOT NULL, filename TEXT NOT NULL,
                content_hash TEXT NOT NULL, format TEXT NOT NULL, layer TEXT NOT NULL DEFAULT 'auto',
                created_at TEXT NOT NULL, profile TEXT NOT NULL DEFAULT '{}', source_content BLOB NOT NULL,
                UNIQUE(repository_id, content_hash)
            );
            CREATE TABLE IF NOT EXISTS echo_validation_reports (
                id TEXT PRIMARY KEY, repository_id TEXT NOT NULL, created_at TEXT NOT NULL,
                fingerprint TEXT NOT NULL, report TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_echo_mappings_node ON echo_mappings(node_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON knowledge_nodes(type);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON knowledge_edges(source_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON knowledge_edges(target_node_id);
            CREATE INDEX IF NOT EXISTS idx_aliases_node ON knowledge_node_aliases(node_id);
            CREATE INDEX IF NOT EXISTS idx_changes_entity ON change_log(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_document ON analysis_jobs(document_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);
            """
        )
        _ensure_column(conn, "extracted_cards", "business_category", "TEXT NOT NULL DEFAULT 'resultat_recherche'")
        _ensure_column(conn, "echo_mappings", "target_signature", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "extracted_cards", "extraction_details", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "extracted_cards", "business_validation_status", "TEXT NOT NULL DEFAULT 'proposed'")
        _ensure_column(conn, "extracted_cards", "business_justification", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "extracted_cards", "archimate_mapping", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "extracted_cards", "archimate_mapping_status", "TEXT NOT NULL DEFAULT 'proposed_by_llm'")
        _ensure_column(conn, "extracted_cards", "ontology_mapping_status", "TEXT NOT NULL DEFAULT 'to_map_later'")
        _ensure_column(conn, "knowledge_nodes", "business_category", "TEXT NOT NULL DEFAULT 'non_qualifie'")
        _ensure_column(conn, "knowledge_nodes", "business_validation_status", "TEXT NOT NULL DEFAULT 'proposed'")
        _ensure_column(conn, "knowledge_nodes", "business_justification", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "knowledge_nodes", "archimate_mapping", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "knowledge_nodes", "archimate_mapping_status", "TEXT NOT NULL DEFAULT 'proposed_by_llm'")
        _ensure_column(conn, "knowledge_nodes", "ontology_mapping_status", "TEXT NOT NULL DEFAULT 'to_map_later'")
        for name, definition in {
            "source_status": "TEXT NOT NULL DEFAULT 'retained'",
            "retention_policy": "TEXT NOT NULL DEFAULT 'keep'",
            "content_hash": "TEXT NOT NULL DEFAULT ''",
            "content_length": "INTEGER NOT NULL DEFAULT 0",
            "source_purged_at": "TEXT",
            "proposed_domain": "TEXT NOT NULL DEFAULT ''",
            "confirmed_domain": "TEXT NOT NULL DEFAULT ''",
            "secondary_domains": "TEXT NOT NULL DEFAULT '[]'",
            "domain_status": "TEXT NOT NULL DEFAULT 'unconfirmed'",
            "domain_evidence": "TEXT NOT NULL DEFAULT '[]'",
        }.items():
            _ensure_column(conn, "source_documents", name, definition)
        conn.execute("""CREATE TABLE IF NOT EXISTS import_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1), retention_policy TEXT NOT NULL DEFAULT 'keep')""")
        conn.execute("INSERT OR IGNORE INTO import_settings (id) VALUES (1)")
        conn.execute("""CREATE TABLE IF NOT EXISTS validation_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1), mode TEXT NOT NULL DEFAULT 'assisted',
            auto_threshold REAL NOT NULL DEFAULT 0.9, review_threshold REAL NOT NULL DEFAULT 0.6)""")
        conn.execute("INSERT OR IGNORE INTO validation_settings (id) VALUES (1)")
        for table in ("extracted_cards", "knowledge_nodes", "knowledge_edges"):
            _ensure_column(conn, table, "business_confidence", "REAL")
            _ensure_column(conn, table, "validation_decision", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(conn, "knowledge_edges", "business_validation_status", "TEXT NOT NULL DEFAULT 'proposed'")
        _ensure_column(conn, "knowledge_nodes", "orphan_status", "TEXT NOT NULL DEFAULT ''")
        conn.execute("""CREATE TABLE IF NOT EXISTS document_references (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
            file_type TEXT NOT NULL, created_at TEXT NOT NULL, content_hash TEXT NOT NULL,
            content_length INTEGER NOT NULL, deleted_at TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}')""")
    from app.services.coherence_service import migrate
    migrate()
    from app.services.review_service import migrate as migrate_review
    migrate_review()


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _ensure_column(
    conn: sqlite3.Connection, table_name: str, column_name: str, column_definition: str
) -> None:
    if column_name in _table_columns(conn, table_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
