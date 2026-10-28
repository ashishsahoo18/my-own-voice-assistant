"""Comprehensive regression tests for OLIVER 2.0 Productivity Assistant (Capability 5)."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config import OliverConfig
from execution.engine import ExecutionEngine
from execution.request import TaskRequest
from execution.verifiers import ProductivityVerifier, VerifierRegistry
from memory.unified_db import UnifiedDatabase
from productivity.datetime_parser import DateTimeParser
from productivity.models import (
    DailyPlan,
    NoteItem,
    RecurrenceType,
    ReminderItem,
    ReminderStatus,
    TaskItem,
    TaskPriority,
    TaskStatus,
)
from productivity.recurrence import RecurrenceEngine
from productivity.scheduler import ProductivityScheduler
from productivity.service import ProductivityService
from productivity.store import ProductivityStore
from security.confirmation import ConfirmationManager
from security.policy_engine import PolicyDecisionType, PolicyEngine
from skills.base import ToolRiskLevel
from skills.builtin.productivity_skill import ProductivitySkill
from skills.registry import SkillRegistry


class TestDateTimeParser(unittest.TestCase):
    """Test date/time parsing, calendar bounds, and DST handling."""

    def test_relative_offsets(self):
        ref = datetime(2026, 10, 15, 12, 0, 0).astimezone()
        # In 15 minutes
        res1 = DateTimeParser.parse("in 15 minutes", reference_dt=ref)
        self.assertEqual(res1, ref + timedelta(minutes=15))

        # In 2 hours
        res2 = DateTimeParser.parse("in 2 hours", reference_dt=ref)
        self.assertEqual(res2, ref + timedelta(hours=2))

        # In 3 days
        res3 = DateTimeParser.parse("in 3 days", reference_dt=ref)
        self.assertEqual(res3, ref + timedelta(days=3))

    def test_tomorrow_and_time(self):
        ref = datetime(2026, 10, 15, 12, 0, 0).astimezone()
        res = DateTimeParser.parse("tomorrow at 3pm", reference_dt=ref)
        self.assertEqual(res.year, 2026)
        self.assertEqual(res.month, 10)
        self.assertEqual(res.day, 16)
        self.assertEqual(res.hour, 15)
        self.assertEqual(res.minute, 0)

    def test_invalid_calendar_dates_rejected(self):
        # February 30 does not exist
        with self.assertRaises(ValueError):
            DateTimeParser.parse("2026-02-30 09:00")

        # April 31 does not exist
        with self.assertRaises(ValueError):
            DateTimeParser.parse("April 31 2026 10am")

    def test_iso_roundtrip_preserves_offset(self):
        now = DateTimeParser.now_local()
        iso_str = DateTimeParser.to_iso(now)
        self.assertTrue("+" in iso_str or "-" in iso_str)
        parsed = DateTimeParser.from_iso(iso_str)
        self.assertEqual(now.isoformat(), parsed.isoformat())


class TestRecurrenceEngine(unittest.TestCase):
    """Test recurring schedule calculations, month-end clamping, and backlog collapsing."""

    def test_daily_and_weekly(self):
        start = datetime(2026, 10, 15, 9, 0, 0).astimezone()
        next_daily = RecurrenceEngine.calculate_next_occurrence(start, "daily")
        self.assertEqual(next_daily, start + timedelta(days=1))

        next_weekly = RecurrenceEngine.calculate_next_occurrence(start, "weekly")
        self.assertEqual(next_weekly, start + timedelta(weeks=1))

    def test_weekdays_skips_weekends(self):
        # Friday Oct 16, 2026 -> should advance to Monday Oct 19, 2026
        friday = datetime(2026, 10, 16, 9, 0, 0).astimezone()
        next_day = RecurrenceEngine.calculate_next_occurrence(friday, "weekdays")
        self.assertEqual(next_day.weekday(), 0)  # Monday
        self.assertEqual(next_day.day, 19)

    def test_month_end_clamping(self):
        # January 31 -> February 28 (2026 is not a leap year)
        jan31 = datetime(2026, 1, 31, 10, 0, 0).astimezone()
        feb = RecurrenceEngine.calculate_next_occurrence(jan31, "monthly")
        self.assertEqual(feb.year, 2026)
        self.assertEqual(feb.month, 2)
        self.assertEqual(feb.day, 28)

    def test_missed_backlog_collapsing(self):
        # Offline for 5 days on a daily reminder
        start = datetime(2026, 10, 10, 9, 0, 0).astimezone()
        now = datetime(2026, 10, 15, 12, 0, 0).astimezone()
        next_future, missed_count = RecurrenceEngine.collapse_missed_recurrences(start, "daily", now)
        self.assertGreater(next_future, now)
        self.assertEqual(missed_count, 6)


class TestProductivityStoreAndCRUD(unittest.TestCase):
    """Test unified database operations for tasks, reminders, and notes."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "oliver_test.db"
        self.db = UnifiedDatabase(db_path=self.db_path)
        self.store = ProductivityStore(self.db)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tasks_crud_lifecycle(self):
        # Create
        task = self.store.create_task(
            title="Complete Capability 5",
            description="Build productivity skill",
            due_date="in 2 hours",
            priority="urgent",
        )
        self.assertIsNotNone(task.id)
        self.assertEqual(task.title, "Complete Capability 5")
        self.assertEqual(task.priority, "urgent")
        self.assertEqual(task.status, TaskStatus.PENDING.value)

        # Update
        updated = self.store.update_task(task.id, priority="high", description="Updated description")
        self.assertEqual(updated.priority, "high")
        self.assertEqual(updated.description, "Updated description")

        # Complete
        completed = self.store.complete_task(task.id)
        self.assertEqual(completed.status, TaskStatus.COMPLETED.value)
        self.assertIsNotNone(completed.completed_at)

        # List
        tasks = self.store.list_tasks(status="completed")
        self.assertEqual(len(tasks), 1)

        # Delete
        deleted = self.store.delete_task(task.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.store.get_task(task.id))

    def test_duplicate_reminder_detection(self):
        # Schedule reminder
        r1 = self.store.add_reminder(title="Drink Water", remind_at="in 30 minutes")
        self.assertIsNotNone(r1.id)

        # Second identical reminder within 60s must raise ValueError
        with self.assertRaises(ValueError):
            self.store.add_reminder(title="Drink Water", remind_at="in 30 minutes")

    def test_notes_fts_search(self):
        # Save notes
        n1 = self.store.save_note(title="Project Alpha", content="Secret encryption keys and quantum algorithms")
        n2 = self.store.save_note(title="Grocery List", content="Milk, eggs, coffee beans, and bread")

        # Search via FTS5
        results_alpha = self.store.search_notes("quantum")
        self.assertEqual(len(results_alpha), 1)
        self.assertEqual(results_alpha[0].id, n1.id)

        results_grocery = self.store.search_notes("coffee")
        self.assertEqual(len(results_grocery), 1)
        self.assertEqual(results_grocery[0].id, n2.id)

        # Delete note cleans up FTS
        self.store.delete_note(n1.id)
        self.assertEqual(len(self.store.search_notes("quantum")), 0)


class TestSchedulerAtomicLeasesAndRecovery(unittest.TestCase):
    """Test database-backed atomic leases, stale recovery, and scheduler lifecycle."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "oliver_sched_test.db"
        self.db = UnifiedDatabase(db_path=self.db_path)
        self.store = ProductivityStore(self.db)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_atomic_lease_prevents_duplicate_claims(self):
        # Create due reminder
        past_iso = DateTimeParser.to_iso(DateTimeParser.now_local() - timedelta(minutes=5))
        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO reminders (title, remind_at, created_at, completed, recurrence, priority, status) "
                "VALUES ('Due Alert', ?, ?, 0, 'none', 'normal', 'pending')",
                (past_iso, past_iso),
            )
            r_id = cur.lastrowid

        now_iso = DateTimeParser.to_iso(DateTimeParser.now_local())

        # Worker 1 claims reminder
        claimed_w1 = self.store.claim_due_reminders(worker_id="worker_1", now_iso=now_iso, lease_seconds=30)
        self.assertEqual(len(claimed_w1), 1)
        self.assertEqual(claimed_w1[0].id, r_id)

        # Worker 2 attempts claiming concurrently -> gets 0 rows
        claimed_w2 = self.store.claim_due_reminders(worker_id="worker_2", now_iso=now_iso, lease_seconds=30)
        self.assertEqual(len(claimed_w2), 0)

    def test_stale_lease_recovery(self):
        # Simulate worker crash: reminder left in 'dispatching' with expired lease
        stale_lease = DateTimeParser.to_iso(DateTimeParser.now_local() - timedelta(minutes=1))
        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO reminders (title, remind_at, created_at, completed, recurrence, priority, status, lease_until, claimed_by) "
                "VALUES ('Crashed Reminder', ?, ?, 0, 'none', 'normal', 'dispatching', ?, 'dead_worker')",
                (stale_lease, stale_lease, stale_lease),
            )
            r_id = cur.lastrowid

        now_iso = DateTimeParser.to_iso(DateTimeParser.now_local())

        # New worker claims it because lease is expired
        reclaimed = self.store.claim_due_reminders(worker_id="live_worker", now_iso=now_iso, lease_seconds=30)
        self.assertEqual(len(reclaimed), 1)
        self.assertEqual(reclaimed[0].id, r_id)
        self.assertEqual(reclaimed[0].status, ReminderStatus.DISPATCHING.value)

    def test_restart_recovery_grace_window_vs_expired(self):
        now = DateTimeParser.now_local()
        # 1. Remind 2 hours ago (within 24h grace window) -> marks 'missed'
        iso_recent = DateTimeParser.to_iso(now - timedelta(hours=2))
        # 2. Remind 48 hours ago (beyond 24h grace window) -> marks 'expired'
        iso_old = DateTimeParser.to_iso(now - timedelta(hours=48))

        with self.db.transaction() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO reminders (title, remind_at, created_at, completed, recurrence, priority, status) "
                "VALUES ('Recent Missed', ?, ?, 0, 'none', 'normal', 'pending')",
                (iso_recent, iso_recent),
            )
            id_recent = cur.lastrowid
            cur.execute(
                "INSERT INTO reminders (title, remind_at, created_at, completed, recurrence, priority, status) "
                "VALUES ('Old Expired', ?, ?, 0, 'none', 'normal', 'pending')",
                (iso_old, iso_old),
            )
            id_old = cur.lastrowid

        stats = self.store.recover_startup_reminders(DateTimeParser.to_iso(now), grace_hours=24.0)
        self.assertEqual(stats["missed"], 1)
        self.assertEqual(stats["expired"], 1)

        r_recent = self.store.get_reminder(id_recent)
        r_old = self.store.get_reminder(id_old)
        self.assertEqual(r_recent.status, ReminderStatus.MISSED.value)
        self.assertEqual(r_old.status, ReminderStatus.EXPIRED.value)

    def test_scheduler_lifecycle_and_single_thread(self):
        dispatched_items = []

        def mock_dispatch(rem: ReminderItem) -> bool:
            dispatched_items.append(rem.id)
            return True

        sched = ProductivityScheduler(
            store=self.store,
            poll_interval=1.0,
            lease_seconds=5.0,
            dispatch_callback=mock_dispatch,
        )

        self.assertFalse(sched.is_running())
        sched.start()
        self.assertTrue(sched.is_running())

        # Second call to start does not spawn duplicate thread
        t1 = sched._thread
        sched.start()
        self.assertIs(sched._thread, t1)

        # Stop cleanly
        sched.stop(timeout=2.0)
        self.assertFalse(sched.is_running())


class TestProductivitySkillAndPolicyPipeline(unittest.TestCase):
    """Test policy gating, confirmation token requirement, and verifier integration."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "oliver_skill_test.db"
        self.db = UnifiedDatabase(db_path=self.db_path)
        self.service = ProductivityService(db=self.db, start_scheduler=False)
        self.skill = ProductivitySkill(service=self.service)

        self.registry = SkillRegistry()
        self.registry.register(self.skill)

        self.policy = PolicyEngine()
        self.engine = ExecutionEngine()

    def tearDown(self):
        self.service.shutdown()
        self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_and_list_tasks_auto_allowed(self):
        req = TaskRequest(
            tool_name="productivity.create_task",
            arguments={"title": "Test Policy Auto Allow", "priority": "high"},
            risk_level=ToolRiskLevel.LOW,
        )
        res = self.engine.execute(req, registry=self.registry)
        self.assertEqual(res.status, "VERIFIED")
        self.assertIn("Task created", res.message)

    def test_delete_task_requires_confirmation_token(self):
        # Create task first
        t = self.service.store.create_task("Sensitive Task")

        # Attempt delete without token -> MUST return NEED_CONFIRM
        req = TaskRequest(
            tool_name="productivity.delete_task",
            arguments={"task_id": t.id},
            risk_level=ToolRiskLevel.SENSITIVE,
        )
        res = self.engine.execute(req, registry=self.registry)
        self.assertEqual(res.status, "NEED_CONFIRM")
        self.assertIn("Permanently delete task", res.message)
        self.assertIsNotNone(res.data.get("token"))

        # Confirm with valid token
        token = res.data["token"]
        confirmed_req = TaskRequest(
            tool_name="productivity.delete_task",
            arguments={"task_id": t.id},
            risk_level=ToolRiskLevel.SENSITIVE,
            confirmation_token=token,
        )
        conf_res = self.engine.execute(confirmed_req, registry=self.registry)
        self.assertEqual(conf_res.status, "VERIFIED")
        self.assertIn("deleted successfully", conf_res.message)
        self.assertIsNone(self.service.store.get_task(t.id))

    def test_delete_reminder_requires_confirmation(self):
        # Create reminder
        r = self.service.store.add_reminder("Sensitive Reminder", "in 10 minutes")

        req = TaskRequest(
            tool_name="productivity.delete_reminder",
            arguments={"reminder_id": r.id},
            risk_level=ToolRiskLevel.SENSITIVE,
        )
        res = self.engine.execute(req, registry=self.registry)
        self.assertEqual(res.status, "NEED_CONFIRM")
        self.assertIn("Permanently delete reminder", res.message)

        # Confirm with valid token
        token = res.data["token"]
        confirmed_req = TaskRequest(
            tool_name="productivity.delete_reminder",
            arguments={"reminder_id": r.id},
            risk_level=ToolRiskLevel.SENSITIVE,
            confirmation_token=token,
        )
        conf_res = self.engine.execute(confirmed_req, registry=self.registry)
        self.assertEqual(conf_res.status, "VERIFIED")
        self.assertIsNone(self.service.store.get_reminder(r.id))

    def test_legacy_math_and_stopwatch(self):
        req_calc = TaskRequest(
            tool_name="productivity.calculate",
            arguments={"expression": "12 * (3 + 7) / 4"},
            risk_level=ToolRiskLevel.SAFE,
        )
        res_calc = self.engine.execute(req_calc, registry=self.registry)
        self.assertEqual(res_calc.status, "VERIFIED")
        self.assertEqual(res_calc.data.get("result"), 30.0)

    def test_daily_plan_aggregation(self):
        # Create a task and reminder due today
        self.service.store.create_task("Daily Task 1", due_date="today at 5pm")
        self.service.store.add_reminder("Daily Reminder 1", remind_at="today at 6pm")

        plan_res = self.skill.get_daily_plan()
        self.assertEqual(plan_res.status, "SUCCESS")
        self.assertIn("Daily Plan", plan_res.message)
        self.assertGreaterEqual(len(plan_res.data.get("tasks_due", [])), 1)
        self.assertGreaterEqual(len(plan_res.data.get("reminders_due", [])), 1)


class TestMigrationV4IdempotencyAndBackup(unittest.TestCase):
    """Test Migration V4 schema upgrade, idempotency, and WAL checkpointing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "oliver_migration_test.db"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_migration_v4_applied_and_idempotent(self):
        # First initialization applies V1 through V4
        db = UnifiedDatabase(db_path=self.db_path)
        ver = db.get_schema_version()
        self.assertGreaterEqual(ver, 4)

        # Check user_tasks table exists
        tasks_row = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name='user_tasks'")
        self.assertEqual(len(tasks_row), 1)

        # Check enhanced columns on reminders table
        cols = {row[1] for row in db.fetch_all("PRAGMA table_info(reminders)")}
        expected_cols = {"recurrence", "priority", "status", "lease_until", "claimed_by", "dispatched_at", "delivery_channels", "dispatch_attempts", "last_error"}
        self.assertTrue(expected_cols.issubset(cols))

        # Check notes_fts virtual table exists
        fts_row = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name='notes_fts'")
        self.assertEqual(len(fts_row), 1)

        # Re-initialize to verify idempotency (must not error)
        db.close()
        db2 = UnifiedDatabase(db_path=self.db_path)
        ver2 = db2.get_schema_version()
        self.assertEqual(ver, ver2)
        db2.close()


if __name__ == "__main__":
    unittest.main()
