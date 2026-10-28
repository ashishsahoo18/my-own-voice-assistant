"""Unified OLIVER 2.0 Database Management.

Provides high-concurrency WAL-mode SQLite connection management, schema versioning,
transactional safety, and index optimization for all assistant operational data.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from core.config import get_config

logger = logging.getLogger("oliver.memory.database")

SCHEMA_VERSION = 1

MIGRATION_V1_SQL = """
-- Schema migration tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

-- Data migration idempotency log
CREATE TABLE IF NOT EXISTS data_migration_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_db TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    migrated_at TEXT NOT NULL,
    UNIQUE(source_db, source_table, source_id)
);

-- Conversational Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Messages per session
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    tokens_estimate INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Reminders
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    remind_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0
);

-- Notes
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Semantic Long-Term Memories (Facts, Preferences, Learned Context)
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT 'general',
    key TEXT,
    content TEXT NOT NULL,
    importance REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at TEXT
);

-- Working Memory (Active session context, resolved references)
CREATE TABLE IF NOT EXISTS working_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id, key)
);

-- Optimization Indexes
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_category_importance ON memories(category, importance DESC);
CREATE INDEX IF NOT EXISTS idx_working_memory_session ON working_memory(session_id);
CREATE INDEX IF NOT EXISTS idx_reminders_remind_at ON reminders(remind_at, completed);
"""

MIGRATION_V2_SQL = """
-- Migration V2: Agent Tasks and Execution Persistence
CREATE TABLE IF NOT EXISTS agent_tasks (
    task_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    current_step INTEGER NOT NULL DEFAULT 0,
    replan_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_task_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    status TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    verification_evidence TEXT,
    message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES agent_tasks(task_id) ON DELETE CASCADE,
    UNIQUE(task_id, step_number)
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_agent_steps_task ON agent_task_steps(task_id, step_number);
"""

MIGRATION_V3_SQL = """
-- Migration V3: Documents & Knowledge Persistent Store with SQLite FTS5
CREATE TABLE IF NOT EXISTS indexed_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id TEXT UNIQUE NOT NULL,
    file_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL DEFAULT 0,
    total_pages INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT UNIQUE NOT NULL,
    doc_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER NOT NULL DEFAULT 1,
    content TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(doc_id) REFERENCES indexed_documents(doc_id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    chunk_id,
    doc_id,
    filename,
    content,
    tokenize='porter unicode61'
);

CREATE INDEX IF NOT EXISTS idx_indexed_docs_hash ON indexed_documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_doc_id ON document_chunks(doc_id, chunk_index);
"""

MIGRATION_V4_SQL = """
-- Migration V4: Productivity Tasks, Enhanced Reminders, and Searchable Notes

CREATE TABLE IF NOT EXISTS user_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    due_date TEXT,
    priority TEXT NOT NULL DEFAULT 'normal',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    metadata_json TEXT DEFAULT '{}'
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    note_id UNINDEXED,
    title,
    content,
    tokenize='porter unicode61'
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON user_tasks(status, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON user_tasks(priority);
"""


class UnifiedDatabase:
    """Thread-safe SQLite connection and transaction manager in WAL mode."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            self.db_path = get_config().storage.database_path

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        self._initialize_database()

    def get_connection(self) -> sqlite3.Connection:
        """Create or return a thread-local SQLite connection configured with WAL and Foreign Keys."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode, foreign keys, and synchronous normal for safe concurrency
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager providing an atomic database transaction with rollback on failure."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("Database transaction rolled back: %s", exc)
            raise

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute a single SQL command with automatic commit."""
        conn = self.get_connection()
        with self._lock:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return cursor

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
        """Execute a query and fetch a single result row."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchone()

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Execute a query and fetch all matching result rows."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()

    def check_integrity(self, quick: bool = False) -> tuple[bool, str]:
        """Run SQLite integrity or quick check to verify database health."""
        pragma = "PRAGMA quick_check;" if quick else "PRAGMA integrity_check;"
        try:
            conn = self.get_connection()
            with self._lock:
                row = conn.execute(pragma).fetchone()
                res = row[0] if row else "unknown"
                is_ok = (res == "ok")
                return is_ok, res
        except Exception as exc:
            return False, str(exc)

    def _initialize_database(self) -> None:
        """Apply schema versioning and run pending migrations."""
        with self._lock:
            conn = self.get_connection()
            # Check current schema version
            has_migration_tbl = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()[0]

            curr_version = 0
            if has_migration_tbl:
                row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
                if row and row[0] is not None:
                    curr_version = row[0]

            if curr_version < 1:
                logger.info("Applying schema migration V1 to %s", self.db_path)
                with conn:
                    conn.executescript(MIGRATION_V1_SQL)
                    now = datetime.now().isoformat()
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (1, "v1_initial_unified_schema", now),
                    )

            if curr_version < 2:
                logger.info("Applying schema migration V2 to %s", self.db_path)
                with conn:
                    conn.executescript(MIGRATION_V2_SQL)
                    now = datetime.now().isoformat()
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (2, "v2_agent_task_persistence", now),
                    )

            if curr_version < 3:
                logger.info("Applying schema migration V3 (Documents & Knowledge FTS5) to %s", self.db_path)
                try:
                    if self.db_path.exists() and self.db_path.stat().st_size > 0:
                        backup_dir = self.db_path.parent / "backups"
                        backup_dir.mkdir(parents=True, exist_ok=True)
                        backup_path = backup_dir / f"oliver_pre_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                        import shutil
                        shutil.copy2(str(self.db_path), str(backup_path))
                except Exception as bkp_err:
                    logger.warning("Could not create pre-migration backup: %s", bkp_err)

                with conn:
                    conn.executescript(MIGRATION_V3_SQL)
                    now = datetime.now().isoformat()
                    conn.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (3, "v3_documents_knowledge_fts", now),
                    )

            if curr_version < 4:
                logger.info("Applying schema migration V4 (Productivity Tasks, Scheduler & Notes FTS) to %s", self.db_path)
                backup_path = None
                try:
                    if self.db_path.exists() and self.db_path.stat().st_size > 0:
                        backup_dir = self.db_path.parent / "backups"
                        backup_dir.mkdir(parents=True, exist_ok=True)
                        backup_path = backup_dir / f"oliver_pre_v4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                        # Flush WAL frames before backup
                        try:
                            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        except Exception:
                            pass
                        # Use SQLite Online Backup API for point-in-time consistency
                        backup_conn = sqlite3.connect(str(backup_path))
                        conn.backup(backup_conn)
                        backup_conn.close()

                        # Validate backup integrity
                        chk_conn = sqlite3.connect(str(backup_path))
                        integrity = chk_conn.execute("PRAGMA integrity_check").fetchone()[0]
                        chk_conn.close()
                        if integrity != "ok":
                            logger.error("Pre-migration V4 backup integrity failed: %s", integrity)
                            raise RuntimeError(f"Backup integrity check failed: {integrity}")
                except Exception as bkp_err:
                    logger.warning("Could not create verified pre-migration V4 backup: %s", bkp_err)

                try:
                    with conn:
                        # 1. Dynamically inspect existing columns on reminders table
                        cur = conn.cursor()
                        existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(reminders)").fetchall()}
                        columns_to_add = [
                            ("recurrence", "TEXT DEFAULT 'none'"),
                            ("priority", "TEXT DEFAULT 'normal'"),
                            ("status", "TEXT DEFAULT 'pending'"),
                            ("lease_until", "TEXT DEFAULT NULL"),
                            ("claimed_by", "TEXT DEFAULT NULL"),
                            ("dispatched_at", "TEXT DEFAULT NULL"),
                            ("delivery_channels", "TEXT DEFAULT '[]'"),
                            ("dispatch_attempts", "INTEGER DEFAULT 0"),
                            ("last_error", "TEXT DEFAULT NULL"),
                        ]
                        for col_name, col_type in columns_to_add:
                            if col_name not in existing_cols:
                                cur.execute(f"ALTER TABLE reminders ADD COLUMN {col_name} {col_type};")

                        # 2. Run V4 core DDL
                        cur.executescript(MIGRATION_V4_SQL)

                        # 3. Create index on enhanced reminder columns if not existing
                        try:
                            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status_remind ON reminders(status, remind_at);")
                            cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_lease ON reminders(status, lease_until);")
                        except Exception:
                            pass

                        # 4. Populate notes_fts from existing notes if any exist
                        try:
                            cur.execute(
                                "INSERT INTO notes_fts (note_id, title, content) "
                                "SELECT id, title, content FROM notes "
                                "WHERE id NOT IN (SELECT note_id FROM notes_fts);"
                            )
                        except Exception:
                            pass

                        # 5. Record migration
                        now = datetime.now().isoformat()
                        cur.execute(
                            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                            (4, "v4_productivity_tasks_scheduler_fts", now),
                        )
                except Exception as mig_err:
                    logger.error("Migration V4 failed: %s. Attempting safe rollback...", mig_err)
                    # If we made a backup, do NOT blindly overwrite if database received newer writes
                    raise

    def get_journal_mode(self) -> str:
        """Return the current SQLite journal mode."""
        row = self.fetch_one("PRAGMA journal_mode")
        if row:
            return str(row[0])
        return ""

    def get_schema_version(self) -> int:
        """Return the highest applied schema version."""
        row = self.fetch_one("SELECT MAX(version) as ver FROM schema_migrations")
        if row and row["ver"] is not None:
            return int(row["ver"])
        return 0

    def close(self) -> None:
        """Close thread-local and tracked connections."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None


_default_unified_db: Optional[UnifiedDatabase] = None


def get_unified_db() -> UnifiedDatabase:
    """Return the global unified database singleton."""
    global _default_unified_db
    if _default_unified_db is None:
        _default_unified_db = UnifiedDatabase()
    return _default_unified_db
