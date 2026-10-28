"""Comprehensive regression tests for Phase 5: Unified Database & Hybrid Memory Engine."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
from pathlib import Path
import unittest

from memory.privacy import SensitiveDataFilter
from memory.unified_db import UnifiedDatabase
from memory.migrator import LegacyDataMigrator
from memory.working_memory import WorkingMemory
from memory.episodic_memory import EpisodicMemory
from memory.semantic_memory import SemanticMemory
from memory.manager import HybridMemoryEngine
from skills.builtin.memory_skill import MemorySkill


class TestPrivacyFilter(unittest.TestCase):
    """Test deterministic privacy filter blocking sensitive data."""

    def setUp(self) -> None:
        self.pf = SensitiveDataFilter()

    def test_clean_text_allowed(self) -> None:
        allowed, reason = self.pf.validate_for_storage("I prefer dark mode and python code")
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_block_api_keys(self) -> None:
        allowed, reason = self.pf.validate_for_storage("My API key is sk-abcdef123456789012345678901234567890")
        self.assertFalse(allowed)
        self.assertIn("API", reason)

    def test_block_bearer_token(self) -> None:
        allowed, reason = self.pf.validate_for_storage("Use Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz12345678901234567890.signature")
        self.assertFalse(allowed)
        self.assertTrue("token" in reason.lower())

    def test_block_passwords(self) -> None:
        allowed, reason = self.pf.validate_for_storage("My password: SuperSecretP@ssw0rd!123")
        self.assertFalse(allowed)
        self.assertIn("Password", reason)

    def test_block_otp_pin(self) -> None:
        allowed, reason = self.pf.validate_for_storage("My verification otp is 987654")
        self.assertFalse(allowed)
        self.assertIn("OTP", reason)

    def test_block_credit_card(self) -> None:
        allowed, reason = self.pf.validate_for_storage("My card number is 4532-1234-5678-9012")
        self.assertFalse(allowed)
        self.assertTrue("card" in reason.lower() or "payment" in reason.lower())

    def test_redaction(self) -> None:
        redacted = self.pf.redact("My password is SuperSecretP@ssw0rd! and otp is 123456")
        self.assertIn("[REDACTED_PASSWORD]", redacted)
        self.assertIn("[REDACTED_OTP]", redacted)


class TestUnifiedDatabaseAndWAL(unittest.TestCase):
    """Test UnifiedDatabase initialization, schema, migrations, and WAL mode."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_oliver.db"
        self.db = UnifiedDatabase(self.db_path)

    def tearDown(self) -> None:
        self.db.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_wal_mode_enabled(self) -> None:
        mode = self.db.get_journal_mode()
        self.assertEqual(mode.lower(), "wal")

    def test_schema_tables_exist(self) -> None:
        tables = [
            "schema_migrations",
            "sessions",
            "messages",
            "reminders",
            "notes",
            "memories",
            "working_memory",
            "data_migration_log",
        ]
        for t in tables:
            row = self.db.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (t,),
            )
            self.assertIsNotNone(row, f"Table {t} should exist in unified schema")

    def test_schema_version_recorded(self) -> None:
        v = self.db.get_schema_version()
        self.assertGreaterEqual(v, 1)

    def test_error_handling_invalid_sql(self) -> None:
        with self.assertRaises(sqlite3.OperationalError):
            self.db.execute("SELECT * FROM non_existent_table_xyz")


class TestLegacyMigrationAndIdempotency(unittest.TestCase):
    """Test additive, idempotent migrations and legacy preservation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.db_dir = self.base_dir / "database"
        self.db_dir.mkdir(parents=True)
        self.backup_dir = self.base_dir / "backups"

        # Create mock legacy ayra_chat.db
        self.legacy_chat_path = self.db_dir / "ayra_chat.db"
        conn = sqlite3.connect(self.legacy_chat_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, created_at TEXT)")
        cur.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp TEXT)")
        cur.execute("INSERT INTO sessions VALUES ('sess_01', 'First Chat', '2026-01-01 10:00:00')")
        cur.execute("INSERT INTO messages VALUES (1, 'sess_01', 'user', 'Hello Oliver', '2026-01-01 10:00:01')")
        cur.execute("INSERT INTO messages VALUES (2, 'sess_01', 'assistant', 'Hello Ashish', '2026-01-01 10:00:02')")
        conn.commit()
        conn.close()

        # Create mock legacy ayra_memory.db
        self.legacy_memory_path = self.db_dir / "ayra_memory.db"
        conn = sqlite3.connect(self.legacy_memory_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE reminders (id INTEGER PRIMARY KEY, text TEXT, time TEXT, is_recurring INTEGER, recurrence_type TEXT, is_active INTEGER, created_at TEXT)")
        cur.execute("INSERT INTO reminders VALUES (1, 'Call Mom', '2026-01-02 12:00:00', 0, 'none', 1, '2026-01-01 10:05:00')")
        conn.commit()
        conn.close()

        # Target unified DB
        self.target_db_path = self.db_dir / "oliver.db"
        self.unified_db = UnifiedDatabase(self.target_db_path)
        self.migrator = LegacyDataMigrator(
            target_db=self.unified_db,
            base_dir=self.base_dir,
            backup_dir=self.backup_dir,
        )

    def tearDown(self) -> None:
        self.unified_db.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_migration_and_legacy_preservation(self) -> None:
        # Check initial legacy data
        report = self.migrator.migrate_all(dry_run=False)
        self.assertEqual(report.total_discovered, 4)
        self.assertEqual(report.total_imported, 4)
        self.assertEqual(report.total_skipped, 0)
        self.assertTrue(report.backup_created)

        # Verify backup files exist
        backup_files = list(self.backup_dir.rglob("*.db"))
        self.assertGreaterEqual(len(backup_files), 2)

        # Verify data in unified DB
        sessions = self.unified_db.fetch_all("SELECT * FROM sessions")
        self.assertEqual(len(sessions), 1)
        self.assertIn("sess_01", sessions[0]["session_id"])

        messages = self.unified_db.fetch_all("SELECT * FROM messages")
        self.assertEqual(len(messages), 2)

        reminders = self.unified_db.fetch_all("SELECT * FROM reminders")
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["title"], "Call Mom")

        # Verify legacy source DBs were NOT deleted or mutated
        conn = sqlite3.connect(self.legacy_chat_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM messages")
        cnt = c.fetchone()[0]
        conn.close()
        self.assertEqual(cnt, 2, "Original legacy messages must remain completely untouched")

    def test_idempotent_rerun_prevents_duplicates(self) -> None:
        # First run
        rep1 = self.migrator.migrate_all(dry_run=False)
        self.assertEqual(rep1.total_imported, 4)

        # Second run immediately after
        rep2 = self.migrator.migrate_all(dry_run=False)
        self.assertEqual(rep2.total_imported, 0)
        self.assertEqual(rep2.total_skipped, 4)

        # Row counts in unified database must NOT increase
        msg_count = self.unified_db.fetch_one("SELECT COUNT(*) as cnt FROM messages")["cnt"]
        self.assertEqual(msg_count, 2)


class TestMemoryTiersAndControls(unittest.TestCase):
    """Test Working Memory, Episodic Memory, Semantic Memory, and Engine Controls."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_tiers.db"
        self.db = UnifiedDatabase(self.db_path)
        self.engine = HybridMemoryEngine(db=self.db)

    def tearDown(self) -> None:
        self.db.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_working_memory_key_value(self) -> None:
        wm = self.engine.working
        wm.set("s1", "current_topic", "astronomy")
        self.assertEqual(wm.get("s1", "current_topic"), "astronomy")
        wm.clear("s1")
        self.assertIsNone(wm.get("s1", "current_topic"))

    def test_working_memory_reference_resolution(self) -> None:
        wm = self.engine.working
        # Track items
        wm.set_candidates("s2", ["report.pdf", "invoice.xlsx", "presentation.pptx"])

        # Resolve pronoun "it" -> refers to most recent / top candidate
        resolved, entity = wm.resolve_reference("open it please", "s2")
        self.assertEqual(entity, "report.pdf")
        self.assertIn('"report.pdf"', resolved)

        # Resolve ordinals
        resolved, entity = wm.resolve_reference("send the second one", "s2")
        self.assertEqual(entity, "invoice.xlsx")
        self.assertIn('"invoice.xlsx"', resolved)

        resolved, entity = wm.resolve_reference("delete the last one", "s2")
        self.assertEqual(entity, "presentation.pptx")
        self.assertIn('"presentation.pptx"', resolved)

    def test_episodic_memory_history_and_clear(self) -> None:
        self.engine.track_turn("sess_a", "Hello Oliver", "Hello Ashish! How can I help?")
        self.engine.track_turn("sess_a", "What time is it?", "It is 4 PM.")

        history = self.engine.episodic.get_session_messages("sess_a")
        self.assertEqual(len(history), 4)

        ctx = self.engine.episodic.get_context_prompt("sess_a")
        self.assertIn("Hello Oliver", ctx)
        self.assertIn("What time is it?", ctx)

        # Clear session
        res = self.engine.clear_session_memory("sess_a")
        self.assertIn("Cleared", res)
        self.assertEqual(len(self.engine.episodic.get_session_messages("sess_a")), 0)

    def test_semantic_memory_crud_and_importance(self) -> None:
        # Add memories
        ok, msg = self.engine.remember("User prefers Python over JavaScript", category="preference", importance=0.9)
        self.assertTrue(ok)
        ok2, _ = self.engine.remember("User works in Seattle", category="facts", importance=0.6)
        self.assertTrue(ok2)

        # Retrieve
        results = self.engine.recall("Python")
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("Python", results[0]["content"])

        # Check what do you remember
        overview = self.engine.what_do_you_remember()
        self.assertIn("Python over JavaScript", overview)
        self.assertIn("Seattle", overview)

        # Forget by content
        f_msg = self.engine.forget("Seattle")
        self.assertIn("Removed", f_msg)
        self.assertEqual(len(self.engine.recall("Seattle")), 0)

        # Forget this memory (most recent)
        f_rec = self.engine.forget("this memory")
        self.assertIn("Forgotten most recent", f_rec)
        self.assertEqual(self.engine.semantic.count(), 0)

    def test_semantic_memory_sensitive_data_rejection(self) -> None:
        ok, msg = self.engine.remember("My password is SuperSecret123!", category="security")
        self.assertFalse(ok)
        self.assertTrue("sensitive" in msg.lower())
        self.assertEqual(self.engine.semantic.count(), 0)

    def test_status_report(self) -> None:
        self.engine.remember("User enjoys tennis", category="hobby")
        self.engine.track_turn("sess_x", "Hi", "Hello")
        st = self.engine.status()
        self.assertEqual(st["total_semantic_memories"], 1)
        self.assertGreaterEqual(st["total_sessions"], 1)
        self.assertGreaterEqual(st["total_messages"], 2)


class TestMemorySkillAndConcurrency(unittest.TestCase):
    """Test MemorySkill integration and multi-threaded database concurrency under WAL mode."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_concurrency.db"
        self.db = UnifiedDatabase(self.db_path)
        self.engine = HybridMemoryEngine(db=self.db)
        self.skill = MemorySkill()
        self.skill.engine = self.engine

    def tearDown(self) -> None:
        self.db.close()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_memory_skill_tools(self) -> None:
        # 1. remember
        res = self.skill.remember("My favorite color is navy blue")
        self.assertEqual(res.status, "SUCCESS")

        # 2. what_do_you_remember
        res = self.skill.what_do_you_remember()
        self.assertEqual(res.status, "SUCCESS")
        self.assertIn("navy blue", res.message)

        # 3. status
        res = self.skill.status()
        self.assertEqual(res.status, "SUCCESS")
        self.assertIn("OLIVER Memory Engine Active", res.message)

        # 4. forget
        res = self.skill.forget("navy blue")
        self.assertEqual(res.status, "SUCCESS")

        # 5. clear_session
        res = self.skill.clear_session("default")
        self.assertEqual(res.status, "SUCCESS")

    def test_concurrent_access_under_wal(self) -> None:
        """Verify multiple threads reading and writing simultaneously do not deadlock."""
        errors: list[Exception] = []

        def worker_task(thread_id: int):
            try:
                # Each thread connects cleanly to the same WAL database
                thread_db = UnifiedDatabase(self.db_path)
                thread_engine = HybridMemoryEngine(db=thread_db)

                for i in range(10):
                    thread_engine.remember(
                        f"Thread {thread_id} preference {i}",
                        category=f"thread_{thread_id}",
                    )
                    thread_engine.track_turn(
                        f"session_{thread_id}",
                        f"User message {i} from thread {thread_id}",
                        f"Bot reply {i}",
                    )
                    # Read
                    thread_engine.recall(f"Thread {thread_id}")

                thread_db.close()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker_task, args=(tid,)) for tid in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent threads experienced errors: {errors}")
        total_mems = self.db.fetch_one("SELECT COUNT(*) as cnt FROM memories")["cnt"]
        self.assertEqual(total_mems, 40)


if __name__ == "__main__":
    unittest.main()
