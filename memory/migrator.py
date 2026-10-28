"""Additive, idempotent data migrator from legacy databases into unified OLIVER SQLite database.

Guarantees:
1. Zero mutation or deletion of legacy database files.
2. Timestamped backup creation before migration.
3. Deterministic tracking via data_migration_log to prevent duplicate imports on repeated runs.
4. Comprehensive migration audit report.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.config import get_config
from memory.unified_db import UnifiedDatabase, get_unified_db

logger = logging.getLogger("oliver.memory.migrator")


@dataclass
class MigrationReport:
    """Summary of data discovery, imports, and skips during migration."""

    backup_dir: Optional[Path] = None
    discovered: dict[str, dict[str, int]] = field(default_factory=dict)
    imported: dict[str, dict[str, int]] = field(default_factory=dict)
    skipped: dict[str, dict[str, int]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def total_discovered(self) -> int:
        return sum(sum(tbls.values()) for tbls in self.discovered.values())

    @property
    def total_imported(self) -> int:
        return sum(sum(tbls.values()) for tbls in self.imported.values())

    @property
    def total_skipped(self) -> int:
        return sum(sum(tbls.values()) for tbls in self.skipped.values())

    @property
    def backup_created(self) -> bool:
        return self.backup_dir is not None


class LegacyDataMigrator:
    """Idempotently imports legacy SQLite records into the unified OLIVER database."""

    def __init__(
        self,
        target_db: Optional[UnifiedDatabase] = None,
        base_dir: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
    ) -> None:
        self.target_db = target_db or get_unified_db()
        self.base_dir = base_dir or get_config().storage.base_dir
        self.custom_backup_dir = backup_dir
        self.legacy_dbs = [
            ("ayra_chat.db", self.base_dir / "database" / "ayra_chat.db"),
            ("ayra_memory.db", self.base_dir / "database" / "ayra_memory.db"),
            ("memory.db", self.base_dir / "database" / "memory.db"),
        ]

    def create_pre_migration_backup(self) -> Path:
        """Create a timestamped backup of legacy database files before migration."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.custom_backup_dir:
            backup_dir = self.custom_backup_dir / f"pre_migration_{timestamp}"
        else:
            backup_dir = self.base_dir / "backups" / f"pre_migration_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        for name, db_path in self.legacy_dbs:
            if db_path.exists():
                dest = backup_dir / name
                shutil.copy2(db_path, dest)
                sha = hashlib.sha256(dest.read_bytes()).hexdigest()
                logger.info("Backed up %s -> %s (SHA-256: %s)", db_path, dest, sha[:12])

        # Also backup target DB if it exists
        if self.target_db.db_path.exists():
            dest = backup_dir / "oliver.db"
            shutil.copy2(self.target_db.db_path, dest)

        return backup_dir

    def migrate_all(self, make_backup: bool = True, dry_run: bool = False) -> MigrationReport:
        """Run idempotent migration over all discovered legacy databases."""
        report = MigrationReport()

        if make_backup and not dry_run:
            report.backup_dir = self.create_pre_migration_backup()

        for db_name, db_path in self.legacy_dbs:
            if not db_path.exists():
                logger.debug("Legacy database not found: %s", db_path)
                continue

            report.discovered[db_name] = {}
            report.imported[db_name] = {}
            report.skipped[db_name] = {}

            try:
                self._migrate_single_db(db_name, db_path, report, dry_run=dry_run)
            except Exception as exc:
                err_msg = f"Failed migrating {db_name}: {exc}"
                logger.error(err_msg, exc_info=True)
                report.errors.append(err_msg)

        return report

    def _migrate_single_db(
        self,
        db_name: str,
        db_path: Path,
        report: MigrationReport,
        dry_run: bool = False,
    ) -> None:
        """Inspect and import tables from a single legacy SQLite database."""
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()

            tables = [
                row[0]
                for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if not row[0].startswith("sqlite_")
            ]

            for tbl in tables:
                rows = cur.execute(f'SELECT * FROM "{tbl}"').fetchall()
                report.discovered[db_name][tbl] = len(rows)
                report.imported[db_name][tbl] = 0
                report.skipped[db_name][tbl] = 0

                for row in rows:
                    row_dict = dict(row)
                    row_id = str(row_dict.get("id", ""))
                    if not row_id:
                        report.skipped[db_name][tbl] += 1
                        continue

                    # Check if already migrated
                    already_migrated = self.target_db.fetch_one(
                        "SELECT id FROM data_migration_log WHERE source_db = ? AND source_table = ? AND source_id = ?",
                        (db_name, tbl, row_id),
                    )
                    if already_migrated:
                        report.skipped[db_name][tbl] += 1
                        continue

                    if dry_run:
                        report.imported[db_name][tbl] += 1
                        continue

                    # Route to appropriate table importer
                    target_table, target_id = self._import_row(db_name, tbl, row_dict)
                    if target_id is not None:
                        # Record in migration log for idempotency
                        now = datetime.now().isoformat()
                        self.target_db.execute(
                            """
                            INSERT INTO data_migration_log
                            (source_db, source_table, source_id, target_table, target_id, status, migrated_at)
                            VALUES (?, ?, ?, ?, ?, 'MIGRATED', ?)
                            """,
                            (db_name, tbl, row_id, target_table, target_id, now),
                        )
                        report.imported[db_name][tbl] += 1
                    else:
                        report.skipped[db_name][tbl] += 1
        finally:
            conn.close()

    def _import_row(
        self,
        db_name: str,
        tbl: str,
        row: dict[str, Any],
    ) -> tuple[str, Optional[int]]:
        """Map and insert a legacy record into the unified schema."""
        now = datetime.now().isoformat()

        # 1. Sessions / Chats
        if tbl in ("chat_sessions", "chats", "sessions"):
            session_id = f"legacy_{db_name.split('.')[0]}_{row['id']}"
            title = row.get("title") or "Imported Conversation"
            created_at = row.get("started_at") or row.get("created_at") or now
            updated_at = row.get("updated_at") or created_at

            cur = self.target_db.execute(
                """
                INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, title, created_at, updated_at),
            )
            return "sessions", cur.lastrowid or 1

        # 2. Messages
        if tbl in ("chat_messages", "messages"):
            legacy_sess_id = row.get("session_id") or row.get("chat_id")
            session_id = f"legacy_{db_name.split('.')[0]}_{legacy_sess_id}"

            # Ensure parent session exists
            self.target_db.execute(
                """
                INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at)
                VALUES (?, 'Imported Conversation', ?, ?)
                """,
                (session_id, row.get("created_at") or now, row.get("created_at") or now),
            )

            role = row.get("role") or "user"
            content = row.get("content") or ""
            created_at = row.get("created_at") or row.get("timestamp") or now

            cur = self.target_db.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, created_at),
            )
            return "messages", cur.lastrowid

        # 3. Reminders
        if tbl == "reminders":
            title = row.get("title") or row.get("text") or row.get("message") or "Reminder"
            remind_at = row.get("remind_at") or row.get("time") or now
            created_at = row.get("created_at") or now
            completed = int(row.get("completed") or row.get("is_done") or 0)

            cur = self.target_db.execute(
                """
                INSERT INTO reminders (title, remind_at, created_at, completed)
                VALUES (?, ?, ?, ?)
                """,
                (title, remind_at, created_at, completed),
            )
            return "reminders", cur.lastrowid

        # 4. Notes
        if tbl == "notes":
            title = row.get("title") or "Note"
            content = row.get("content") or ""
            created_at = row.get("created_at") or now
            updated_at = row.get("updated_at") or created_at

            cur = self.target_db.execute(
                """
                INSERT INTO notes (title, content, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (title, content, created_at, updated_at),
            )
            return "notes", cur.lastrowid

        # 5. Semantic Memories
        if tbl == "memory":
            category = row.get("category") or "general"
            content = row.get("content") or ""
            importance = float(row.get("importance") or 0.5)
            created_at = row.get("created_at") or now
            updated_at = row.get("updated_at") or created_at

            cur = self.target_db.execute(
                """
                INSERT INTO memories (category, content, importance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (category, content, importance, created_at, updated_at),
            )
            return "memories", cur.lastrowid

        return "unknown", None
