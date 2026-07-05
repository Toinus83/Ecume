from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from typing import Iterator

from app.config import DATA_DIR, DB_PATH, EXPORT_DIR, UPLOAD_DIR


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
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
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON knowledge_nodes(type);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON knowledge_edges(source_node_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON knowledge_edges(target_node_id);
            CREATE INDEX IF NOT EXISTS idx_aliases_node ON knowledge_node_aliases(node_id);
            CREATE INDEX IF NOT EXISTS idx_changes_entity ON change_log(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_document ON analysis_jobs(document_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON analysis_jobs(status);
            """
        )
