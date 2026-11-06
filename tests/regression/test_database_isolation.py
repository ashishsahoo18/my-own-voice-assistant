"""Automated regression tests proving database and LLM isolation (Phase 1.10).

Verifies that unit tests and simulated operations never touch or modify production databases,
tests dependency injection for ProductivityService and KnowledgeStore,
validates multi-thread connection sharing, and verifies knowledge retrieval and citations.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from core.config import get_config
from knowledge.chunker import DocumentChunker
from knowledge.models import DocumentSearchResult
from knowledge.security import DocumentSecurity
from knowledge.service import KnowledgeService
from knowledge.store import KnowledgeStore
from llm.provider import DummyLLMProvider
from memory.unified_db import (
    UnifiedDatabase,
    get_unified_db,
    isolated_test_db,
    reset_unified_db,
    set_unified_db,
)
from productivity.models import TaskPriority, TaskStatus
from productivity.service import (
    ProductivityService,
    get_productivity_service,
    reset_productivity_service,
    set_productivity_service,
)
from security.sandbox import PathSandbox


class DatabaseIsolationRegressionTests(unittest.TestCase):
    """Regression test suite ensuring zero-leakage to production databases."""

    def setUp(self) -> None:
        self.prod_db_path = get_config().storage.database_path
        self.initial_prod_stat = (
            self.prod_db_path.stat().st_mtime if self.prod_db_path.exists() else None
        )
        # Snapshot production database row counts if it exists
        self.initial_prod_counts = self._get_table_counts(self.prod_db_path)

    def _get_table_counts(self, db_path: Path) -> dict[str, int]:
        if not db_path.exists():
            return {}
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [r[0] for r in cur.fetchall()]
        counts = {}
        for t in tables:
            try:
                cur.execute(f'SELECT count(*) FROM "{t}"')
                counts[t] = cur.fetchone()[0]
            except Exception:
                pass
        conn.close()
        return counts

    def _assert_production_db_untouched(self) -> None:
        """Verify production database has identical table counts and has not been written to."""
        current_counts = self._get_table_counts(self.prod_db_path)
        self.assertEqual(
            self.initial_prod_counts,
            current_counts,
            "Production database row counts changed during test execution!",
        )
        if self.prod_db_path.exists() and self.initial_prod_stat is not None:
            self.assertEqual(
                self.initial_prod_stat,
                self.prod_db_path.stat().st_mtime,
                "Production database mtime changed during test execution!",
            )

    def test_isolated_test_db_creates_temp_file_and_leaves_prod_untouched(self) -> None:
        """isolated_test_db must generate a unique SQLite file and redirect get_unified_db()."""
        with isolated_test_db() as (test_db, temp_path):
            self.assertTrue(temp_path.exists())
            self.assertNotEqual(temp_path.resolve(), self.prod_db_path.resolve())
            self.assertEqual(get_unified_db().db_path.resolve(), temp_path.resolve())

            # Write test record into isolated DB
            test_db.execute(
                "INSERT INTO notes (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("Test Note", "Isolated note content", "2026-11-06T00:00:00", "2026-11-06T00:00:00"),
            )
            row = test_db.fetch_one("SELECT count(*) FROM notes")
            self.assertEqual(row[0], 1)

        # After exiting context, temp path must be cleaned up and production DB untouched
        self.assertFalse(temp_path.exists())
        self._assert_production_db_untouched()

    def test_productivity_service_db_path_injection(self) -> None:
        """ProductivityService must accept db_path and never touch production database."""
        temp_dir = tempfile.mkdtemp(prefix="oliver_prod_svc_test_")
        test_db_path = Path(temp_dir) / "custom_prod.db"
        try:
            service = ProductivityService(db_path=test_db_path, start_scheduler=False)
            self.assertEqual(service.db.db_path.resolve(), test_db_path.resolve())

            # Perform productivity CRUD
            task = service.store.create_task(
                title="Isolation Task",
                description="Must stay in custom_prod.db",
                due_date="in 1 hour",
                priority=TaskPriority.HIGH.value,
            )
            self.assertIsNotNone(task.id)

            note = service.store.save_note(
                title="Isolation Note",
                content="Sensitive test note content",
            )
            self.assertIsNotNone(note.id)

            # Confirm records exist in custom test DB
            tasks = service.store.list_tasks()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].title, "Isolation Task")

            notes = service.store.search_notes("Sensitive")
            self.assertEqual(len(notes), 1)
            self.assertEqual(notes[0].title, "Isolation Note")

            service.shutdown()
            service.db.close()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self._assert_production_db_untouched()

    def test_productivity_service_unified_db_injection(self) -> None:
        """ProductivityService must accept pre-instantiated UnifiedDatabase."""
        with isolated_test_db() as (custom_db, _):
            service = ProductivityService(db=custom_db, start_scheduler=False)
            self.assertIs(service.db, custom_db)

            reminder = service.store.add_reminder(
                title="Doctor appointment",
                remind_at="in 3 hours",
            )
            self.assertIsNotNone(reminder.id)

            reminders = service.list_reminders()
            self.assertEqual(len(reminders), 1)
            self.assertEqual(reminders[0].title, "Doctor appointment")

            service.shutdown()

        self._assert_production_db_untouched()

    def test_multithreaded_test_db_connections_share_data(self) -> None:
        """Multiple threads querying the isolated test database file must observe identical state."""
        with isolated_test_db() as (test_db, temp_path):
            errors = []

            def worker_writer(tid: int) -> None:
                try:
                    conn = sqlite3.connect(str(temp_path))
                    conn.execute(
                        "INSERT INTO notes (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (f"ThreadNote {tid}", f"Content from thread {tid}", "2026-11-06", "2026-11-06"),
                    )
                    conn.commit()
                    conn.close()
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker_writer, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [])
            rows = test_db.fetch_all("SELECT count(*) FROM notes")
            self.assertEqual(rows[0][0], 5)

        self._assert_production_db_untouched()

    def test_dummy_llm_provider_isolation(self) -> None:
        """DummyLLMProvider must return canned and structured responses without any server or network."""
        provider = DummyLLMProvider(canned_response="Local AI is offline. Simulated response.")
        is_healthy, url, model, models, err = provider.check_health()
        self.assertTrue(is_healthy)
        self.assertEqual(url, "mock://localhost:11434")

        ans = provider.ask("What is quantum computing?")
        self.assertEqual(ans, "Local AI is offline. Simulated response.")
        self.assertEqual(len(provider.call_history), 1)

        # Test offline simulation
        offline_provider = DummyLLMProvider(is_healthy=False, error_message="Simulated offline error.")
        is_h, _, _, _, err_msg = offline_provider.check_health()
        self.assertFalse(is_h)
        self.assertIn("Simulated offline error", err_msg)
        self.assertIn("Simulated offline error", offline_provider.ask("Hello?"))

    def test_knowledge_retrieval_and_citations_in_isolated_db(self) -> None:
        """Task 4 verification: Index TXT/MD files, search FTS5, retrieve citations in isolated DB."""
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        test_root = Path(temp_dir.name).resolve()
        try:
            test_db_path = test_root / "isolated_knowledge.db"
            isolated_db = UnifiedDatabase(db_path=test_db_path)
            store = KnowledgeStore(db=isolated_db)
            sandbox = PathSandbox(allowed_roots=[test_root])
            security = DocumentSecurity(sandbox=sandbox)

            mock_ai = DummyLLMProvider(
                canned_response="Asynchronous programming in Python uses asyncio event loops. [async_guide.md, Page 1]"
            )
            service = KnowledgeService(
                store=store,
                security=security,
                ai_service=mock_ai,
                chunker=DocumentChunker(chunk_size=200, overlap=30),
            )

            # 1. Create test TXT and MD documents
            txt_file = test_root / "notes.txt"
            txt_file.write_text(
                "OLIVER 2.0 provides isolated test suites and verifiable execution logs.\n"
                "SQLite FTS5 provides fast BM25 full-text ranking across indexed document chunks.",
                encoding="utf-8",
            )

            md_file = test_root / "async_guide.md"
            md_file.write_text(
                "# Python Asynchronous Guide\n\n"
                "Python asynchronous programming is built on coroutines and async/await syntax.\n"
                "The event loop executes tasks cooperatively without OS thread overhead.\n\n"
                "---\n\n"
                "## Advanced Concurrency\n"
                "Use asyncio.gather to run concurrent background coroutines safely.",
                encoding="utf-8",
            )

            # 2. Verify indexing
            ok_txt, msg_txt, meta_txt = service.index_file(str(txt_file))
            self.assertTrue(ok_txt)
            self.assertEqual(meta_txt.filename, "notes.txt")
            self.assertGreater(meta_txt.total_chunks, 0)

            ok_md, msg_md, meta_md = service.index_file(str(md_file))
            self.assertTrue(ok_md)
            self.assertEqual(meta_md.filename, "async_guide.md")
            self.assertEqual(meta_md.total_pages, 2)

            # 3. Verify SQLite FTS5 storage
            fts_rows = isolated_db.fetch_all("SELECT count(*) FROM document_chunks_fts")
            self.assertGreater(fts_rows[0][0], 0)

            doc_rows = isolated_db.fetch_all("SELECT count(*) FROM indexed_documents")
            self.assertEqual(doc_rows[0][0], 2)

            # 4. Verify search results and relevance
            search_res = service.search("asynchronous coroutines")
            self.assertGreater(search_res.total_matches, 0)
            self.assertEqual(search_res.matches[0].chunk.filename, "async_guide.md")
            self.assertIn("async/await", search_res.matches[0].chunk.content)

            # 5. Verify source citation output in format_markdown
            md_formatted = search_res.format_markdown()
            self.assertIn("async_guide.md", md_formatted)
            self.assertIn("Score:", md_formatted)

            # 6. Verify grounded Q&A with citations
            qa_res = service.ask("How does asynchronous programming work in Python?")
            self.assertTrue(qa_res.has_sufficient_evidence)
            self.assertGreater(len(qa_res.citations), 0)
            self.assertEqual(qa_res.citations[0].filename, "async_guide.md")
            self.assertEqual(qa_res.citations[0].page_number, 1)
            self.assertIn("[async_guide.md, Page 1]", qa_res.answer)

            # 7. Close and verify
            isolated_db.close()
        finally:
            temp_dir.cleanup()

        self._assert_production_db_untouched()

    def test_empty_knowledge_index_behavior(self) -> None:
        """Empty knowledge store must gracefully return zero matches and appropriate messages."""
        with isolated_test_db() as (test_db, _):
            store = KnowledgeStore(db=test_db)
            service = KnowledgeService(store=store)

            res = service.search("anything")
            self.assertEqual(res.total_matches, 0)
            self.assertEqual(len(res.matches), 0)

            qa_res = service.ask("What is recursion?")
            self.assertFalse(qa_res.has_sufficient_evidence)
            self.assertEqual(qa_res.citations, [])
            self.assertIn("No relevant passages found", qa_res.answer)

        self._assert_production_db_untouched()


if __name__ == "__main__":
    unittest.main()

