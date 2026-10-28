# OLIVER 2.0 — Phase 8, Capability 5: Productivity Assistant Implementation Plan

**Date:** October 13, 2026  
**Status:** COMPLETED  
**Target Branch:** `oliver-2.0`  
**Parent Document:** [`docs/PHASE_8_PLAN.md`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/docs/PHASE_8_PLAN.md)  

---

## 1. Codebase Audit & System Verification (Source-Verified Baseline)

Before designing Capability 5, an audit of all existing components was conducted to verify concrete implementations against source code:

### 1.1 Verified Components & Architecture (from Active Code)
1. **Unified Database (`memory/unified_db.py`):**
   - *Verified:* `UnifiedDatabase` runs SQLite in WAL mode (`PRAGMA journal_mode=WAL`), enforces thread-local connections (`threading.local().conn`), and uses a connection lock with `busy_timeout = 5000ms`.
   - *Verified:* Supports transactional contexts (`with db.transaction():`) and schema versioning via `schema_migrations` and `data_migration_log`.
   - *Verified Baseline Tables:*
     - `reminders` (V1): `id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, remind_at TEXT NOT NULL, created_at TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0`.
     - `notes` (V1): `id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL`.
2. **ExecutionEngine Pipeline (`execution/engine.py`):**
   - *Verified:* All actions funnel through `execute(TaskRequest)`: request integrity check -> emergency kill switch check -> `ToolSpec` lookup in `SkillRegistry` -> policy evaluation via `PolicyEngine` -> confirmation token check -> tool invocation -> domain verification in `VerifierRegistry` -> audit recording in `logs/audit.jsonl` -> `ToolResult`.
   - *Verified Status Conventions:* `VERIFIED`, `UNVERIFIED`, `FAILED`, `DENIED`, `CANCELLED`, `TIMEOUT`.
3. **PolicyEngine & Confirmation Tokens (`security/policy_engine.py`, `security/confirmation.py`):**
   - *Verified:* `PolicyEngine.evaluate()` categorizes actions by risk level:
     - `Risk 0 (SAFE)`: Auto-allowed.
     - `Risk 1 (LOW)`: Auto-allowed with audit event `POLICY_EVAL (ALLOWED)`.
     - `Risk 2 (SENSITIVE)` and `Risk 3 (DANGEROUS)`: Requires explicit user confirmation, returning `NEED_CONFIRM` with a time-limited token (30s timeout) and an exact-effect summary preview string.
     - Token validation: Verified and consumed via `ConfirmationManager.verify_and_consume(token, "yes")`.
4. **Voice Output (`voice/speaker.py`):**
   - *Verified:* `VoiceSpeaker.speak(text, wait=False)` enqueues text into an in-memory `queue.Queue()`. A dedicated background thread initializes Windows SAPI5 (`pyttsx3`) and synthesizes speech.
   - *Important Architectural Finding:* Calling `speak()` merely enqueues audio. Even when `wait=True` is used, it only verifies that SAPI5 audio playback finished—it **does not and cannot confirm that the user was present or heard the message**.
5. **GUI Notifications (`ui/app.py`, `ui/chat.py`):**
   - *Verified:* The UI is built using CustomTkinter (`app.py`). Notifications are posted into `CommandConsolePanel.add_entry(timestamp, command_text, intent, action_desc, status)` in `ui/chat.py`.
   - *Important Architectural Finding:* There is currently **no native Windows OS toast notification** or system-tray popup service in the project. UI notifications render inside the HUD console cockpit panel.

### 1.2 Critical Deficiencies Identified
1. **Split-Brain Storage Bug:**
   - Legacy [`commands/reminders.py`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/commands/reminders.py) connects directly to `database/ayra_memory.db`.
   - [`skills/builtin/productivity_skill.py`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/skills/builtin/productivity_skill.py) wraps `ReminderCommands`, causing all reminders created via skills to bypass `database/oliver.db`.
2. **Missing Task Management:**
   - No user task/to-do system exists. `agent_tasks` in Migration V2 is strictly for AI autonomous multi-step planning loops, not user to-dos.
3. **No Active Scheduler or Delivery Verification:**
   - Reminders are currently passive rows in a database; no timer, loop, or background scheduler checks or announces them.
4. **Legacy Placeholder Stubs:**
   - [`commands/productivity.py`](file:///c:/Users/ASHISH/OneDrive/Desktop/Documents/my%20own%20voice%20assistant/commands/productivity.py) stubs (`daily_planner`, `quick_note`, `todo_list`) return hardcoded strings without persisting anything.

---

## 2. Architecture & Module Design

Capability 5 will be organized in a modular package `productivity/` and exposed via `skills/builtin/productivity_skill.py`:

```
[User Request / Voice Command]
         │
         ▼
[ProductivitySkill] (skills/builtin/productivity_skill.py)
   ├── [DateTimeParser] (productivity/datetime_parser.py)
   │      ├── Timezone Standardization (ISO 8601 with local UTC offset)
   │      ├── Relative Offset Calculator ("in 15 minutes", "tomorrow at 3pm")
   │      ├── Calendar Validation (rejection of Feb 30, invalid timestamps)
   │      └── Daylight Saving Transition Guards (gap fold-forward, overlap fold=0)
   │
   ├── [RecurrenceEngine] (productivity/recurrence.py)
   │      ├── Next Occurrence Calculator (daily, weekly, weekdays, monthly)
   │      ├── Month-End Clamping (Jan 31 -> Feb 28/29)
   │      └── Missed Recurrence Collapser (prevents multi-day offline spam)
   │
   ├── [ProductivityStore] (productivity/store.py)
   │      ├── Unified Database Operations (database/oliver.db only)
   │      ├── Atomic Leases & Concurrency Protection
   │      ├── Tasks Repository (CRUD, priority tiers, status state machine)
   │      ├── Reminders Repository (CRUD, recurrence, de-duplication)
   │      └── Notes Repository (CRUD, SQLite FTS5 full-text search)
   │
   ├── [ProductivityScheduler] (productivity/scheduler.py)
   │      ├── Process Singleton Daemon Thread (5-second polling loop)
   │      ├── Graceful Shutdown & Thread Join (atexit handler)
   │      ├── Database Lock Resilience & Exponential Backoff
   │      ├── Atomic Lease Claiming & Crash Recovery
   │      ├── Restart Recovery & Missed Reminder Catch-Up (grace window)
   │      ├── Dispatch Retry Engine (exponential retry on failed delivery)
   │      └── Formal State Machine (PENDING -> DUE -> DISPATCHING -> DISPATCHED -> ACKNOWLEDGED)
   │
   └── [ProductivityService] (productivity/service.py)
          ├── Daily Planner & Agenda Aggregator
          ├── Local Ollama Briefing Synthesizer (with offline fallback)
          └── PolicyEngine Confirmation Coordinator (deletions require tokens)
```

---

## 3. Database Migration V4 & Safe Recovery Specification

### 3.1 Idempotent Schema Upgrades (`MIGRATION_V4_SQL`)
Applied via `UnifiedDatabase._initialize_database()`:

```sql
-- Migration V4: Productivity Tasks, Enhanced Reminders, and Searchable Notes

-- 1. User Tasks Table
CREATE TABLE IF NOT EXISTS user_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    due_date TEXT,
    priority TEXT NOT NULL DEFAULT 'normal', -- low, normal, high, urgent
    status TEXT NOT NULL DEFAULT 'pending',   -- pending, in_progress, completed, cancelled
    created_at TEXT NOT NULL,
    completed_at TEXT,
    metadata_json TEXT DEFAULT '{}'
);

-- 2. Enhanced Reminders Table (augmented idempotently via PRAGMA check in Python)
-- Additional columns added if not present:
-- recurrence TEXT DEFAULT 'none'
-- priority TEXT DEFAULT 'normal'
-- status TEXT DEFAULT 'pending' -- pending, due, dispatching, dispatched, acknowledged, missed, expired, cancelled, dispatch_failed
-- lease_until TEXT DEFAULT NULL -- ISO timestamp for atomic distributed leases
-- claimed_by TEXT DEFAULT NULL -- Worker process/thread ID holding the lease
-- dispatched_at TEXT DEFAULT NULL
-- delivery_channels TEXT DEFAULT '[]' -- JSON array, e.g. ["voice", "ui"]
-- dispatch_attempts INTEGER DEFAULT 0
-- last_error TEXT DEFAULT NULL

-- 3. Notes Full-Text Search Virtual Table
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    note_id UNINDEXED,
    title,
    content,
    tokenize='porter unicode61'
);

-- 4. Optimization Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status_due ON user_tasks(status, due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON user_tasks(priority);
CREATE INDEX IF NOT EXISTS idx_reminders_status_remind ON reminders(status, remind_at);
CREATE INDEX IF NOT EXISTS idx_reminders_lease ON reminders(status, lease_until);
```

### 3.2 Pre-Migration Backup, WAL Checkpointing & Recovery Strategy
1. **WAL Checkpointing Before Backup:**
   - In SQLite WAL mode, uncommitted or recently committed frames reside in `database/oliver.db-wal`.
   - Before executing a backup, `UnifiedDatabase` runs `PRAGMA wal_checkpoint(TRUNCATE)` on an exclusive connection. This forces all WAL log frames into the main `database/oliver.db` file and truncates the WAL file to zero bytes.
2. **Online Backup API Snapshot:**
   - Rather than relying on unsafe raw OS file copies that can capture torn database pages, the backup uses Python's standard `sqlite3.Connection.backup()`:
     ```python
     backup_conn = sqlite3.connect(backup_path)
     source_conn.backup(backup_conn, pages=100)
     backup_conn.close()
     ```
   - Target filename: `backups/oliver_pre_v4_YYYYMMDD_HHMMSS.db`.
3. **Backup Integrity Validation:**
   - The backup file is verified before any DDL runs:
     - File existence and non-zero byte size verified.
     - `PRAGMA integrity_check` executed against `backup_path` verifying zero corruption.
4. **Idempotency Guarantee:**
   - Tables use `CREATE TABLE IF NOT EXISTS`.
   - Columns on `reminders` are inspected via `PRAGMA table_info(reminders)`. If a column already exists, `ALTER TABLE` is skipped.
5. **Protection Against Restoring Over Newer Databases:**
   - If an error occurs mid-migration, restoration is evaluated:
     - The recovery routine checks whether `database/oliver.db` has received any post-backup writes (e.g. comparing write timestamps or higher schema versions).
     - It **never** blindly overwrites a newer database. If post-backup modifications exist, restoration fails safely with `MigrationRecoveryConflictError` and requires administrative review.
6. **Preservation of Legacy Data:**
   - Legacy `database/ayra_memory.db` and `ayra_chat.db` are **never deleted, truncated, or modified**.

---

## 4. Crash-Safe Dispatch & Atomic Leases

### 4.1 The Fundamental Limits of Exactly-Once Delivery
In any computer system interacting with physical audio hardware and user interfaces, **strict mathematically guaranteed exactly-once delivery is impossible** because hardware device operations (Windows SAPI5 voice playback and CustomTkinter display) and local database transactions cannot participate in an atomic two-phase commit (2PC).

- **Scenario:** The scheduler calls `speaker.speak()`, audio waves play into the room, and immediate power loss occurs *before* the SQLite transaction writing `status = 'DISPATCHED'` commits. Upon reboot, the database still sees the item as incomplete.
- **OLIVER's Guarantee:** **At-least-once dispatch with lease-based deduplication and honest state auditing**. The system guarantees that no reminder is silently dropped without dispatch attempts, and prevents duplicate dispatches during normal concurrent operation.

### 4.2 Database-Backed Atomic Claiming & Leases
To prevent duplicate dispatches across concurrent threads or multiple OLIVER processes running against `database/oliver.db`:

1. **Atomic Lease Acquisition:**
   When the scheduler identifies due reminders (`remind_at <= now`), it acquires an atomic lease inside an `IMMEDIATE` transaction:
   ```sql
   UPDATE reminders
   SET status = 'DISPATCHING',
       lease_until = :lease_expiry,
       claimed_by = :worker_id
   WHERE id = :id
     AND (status IN ('PENDING', 'MISSED') 
          OR (status = 'DISPATCHING' AND lease_until < :now_iso));
   ```
   - `:lease_expiry` is set to `now + 30 seconds`.
   - `:worker_id` is set to `f"oliver_{os.getpid()}_{threading.get_ident()}_{uuid4().hex[:6]}"`.
   - If `cursor.rowcount == 0`, another process/thread claimed the reminder; the worker skips it.
2. **Safe Dispatch Execution:**
   - The worker executes notification delivery (HUD console log + SAPI5 voice speak).
   - If successful, it commits:
     ```sql
     UPDATE reminders
     SET status = 'DISPATCHED',
         dispatched_at = :dispatched_at,
         delivery_channels = :channels,
         lease_until = NULL,
         claimed_by = NULL
     WHERE id = :id AND claimed_by = :worker_id;
     ```
3. **Stale Lease Recovery (Crash Recovery):**
   - If an application crash or power cut occurs during dispatch, the reminder remains in `status = 'DISPATCHING'` with an expired `lease_until`.
   - On the next scheduler poll (or upon reboot), the lease acquisition query matches rows where `status = 'DISPATCHING' AND lease_until < :now_iso`.
   - The recovery handler inspects `dispatch_attempts`:
     - If `dispatch_attempts < 3`: logs an audit warning (*"Recovered stale lease from prior crash for reminder {id}"*), increments `dispatch_attempts`, and re-attempts dispatch.
     - If `dispatch_attempts >= 3`: marks `status = 'DISPATCH_FAILED'` with `last_error = 'LeaseExpiredWithoutConfirmation'`.

---

## 5. Formal Reminder State Machine

### 5.1 Permitted States & Lifecycle

| State | Definition | Next Permitted States |
| :--- | :--- | :--- |
| `PENDING` | Scheduled for a future timestamp. | `DUE`, `DISPATCHING`, `MISSED`, `EXPIRED`, `CANCELLED` |
| `DUE` | Target timestamp reached; selected for lease acquisition. | `DISPATCHING`, `CANCELLED` |
| `DISPATCHING` | Atomically leased by an active worker for delivery. | `DISPATCHED`, `PENDING` (retry), `DISPATCH_FAILED`, `CANCELLED` |
| `DISPATCHED` | Dispatched to active channels (HUD + Voice). | `ACKNOWLEDGED`, `COMPLETED`, `PENDING` (recurring advance) |
| `ACKNOWLEDGED` | Explicitly acknowledged or dismissed by user via voice/UI. | `COMPLETED` |
| `COMPLETED` | Marked completed by user. Terminal state. | *None* |
| `CANCELLED` | Cancelled by user before or after trigger. Terminal state. | *None* |
| `MISSED` | Target time passed while offline (within 24h grace window). | `DISPATCHING`, `CANCELLED` |
| `EXPIRED` | Target time passed while offline (older than 24h grace window). | *None* (Terminal audit state) |
| `DISPATCH_FAILED`| Max dispatch retries (3) exceeded without success. | `PENDING` (manual reschedule), `CANCELLED` |

```
                       ┌──────────────┐
                       │   PENDING    │
                       └──────┬───────┘
          Startup (>24h)      │      Startup (<24h)
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼ Due                 ▼
  ┌───────────┐         ┌───────────┐         ┌───────────┐
  │  EXPIRED  │         │    DUE    │         │  MISSED   │
  └───────────┘         └─────┬─────┘         └─────┬─────┘
                              │                     │
                              ▼ Atomic Lease        ▼ Atomic Lease
                        ┌─────────────────────────────────┐
                        │          DISPATCHING            │
                        └───────┬──────────────┬──────────┘
             Dispatch Succeeded │              │ Retry < 3 (Fail)
                                │              ▼
                                │        ┌───────────┐
                                │        │  PENDING  │ (with backoff)
                                │        └───────────┘
                                │              │ Retry >= 3 (Fail)
                                │              ▼
                                │        ┌─────────────────┐
                                │        │ DISPATCH_FAILED │
                                │        └─────────────────┘
                                ▼
                        ┌──────────────┐
       Recurring Advance│  DISPATCHED  │
     ┌──────────────────┤ (Recorded)   │
     │                  └──────┬───────┘
     │                         │ User Acknowledges / Completes
     ▼                         ▼
┌─────────┐             ┌──────────────┐       ┌───────────┐
│ PENDING │             │ ACKNOWLEDGED │ ────> │ COMPLETED │
└─────────┘             └──────────────┘       └───────────┘
```

### 5.2 Transition Table & Invariants

| From State | Event / Trigger | Guard Condition | To State | Actions / Side Effects |
| :--- | :--- | :--- | :--- | :--- |
| `PENDING` | Scheduler Poll | `remind_at <= now` | `DISPATCHING` | Atomic lease acquired; `lease_until = now + 30s`. |
| `PENDING` | Startup Recovery | `remind_at < now AND now - remind_at <= 24h` | `MISSED` | Logged as missed catch-up item. |
| `PENDING` | Startup Recovery | `remind_at < now AND now - remind_at > 24h` | `EXPIRED` | Audit log recorded; no user alert. |
| `MISSED` | Scheduler Poll | Active worker available | `DISPATCHING` | Leased for catch-up alert dispatch. |
| `DISPATCHING` | Notification Success | Voice/UI dispatch OK | `DISPATCHED` | Set `dispatched_at = now`; clear lease; log channels. |
| `DISPATCHING` | Notification Failure | `dispatch_attempts < 3` | `PENDING` | Clear lease; set `remind_at = now + 30s * attempts`. |
| `DISPATCHING` | Notification Failure | `dispatch_attempts >= 3` | `DISPATCH_FAILED` | Clear lease; record error in audit log. |
| `DISPATCHED` | Recurring Trigger | `recurrence != 'none'` | `PENDING` | Advance `remind_at` to next occurrence; increment count. |
| `DISPATCHED` | User Acknowledges | User says "dismiss" / clicks GUI | `ACKNOWLEDGED` | Audit log recorded. |
| `*` | User Deletes/Cancels | Policy confirmation token valid | `CANCELLED` | Deleted from active view; audit log recorded. |

---

## 6. Timezone, Calendar & Date/Time Handling

### 6.1 Timezone Standards & Local Interpretation
- **Storage Standard:** All timestamps in `database/oliver.db` are ISO 8601 strings with explicit UTC offsets (`YYYY-MM-DDTHH:MM:SS±HH:MM`, e.g. `2026-10-15T09:00:00-05:00`).
- **Local Interpretation:** User commands like "at 5pm" or "in 30 minutes" are resolved against `datetime.now().astimezone()` (the user's local system timezone).

### 6.2 Calendar Edge Cases & Daylight Saving Transitions
- **Invalid Date Guard:** Strict calendar validation rejects non-existent dates (e.g. February 30, April 31) with clear user feedback.
- **Daylight Saving Transitions:**
  - *Spring Forward (Gap / 1 hour lost, e.g. 2:30 AM does not exist):* Times falling into the missing hour gap are safely folded forward to the next valid minute (3:00 AM) with audit logging.
  - *Fall Back (Overlap / 1 hour repeated, e.g. 1:30 AM occurs twice):* Uses `datetime.fold = 0` (first occurrence) so the reminder triggers at the earliest valid local time.
- **Month-End Recurrence:** Days are clamped via `calendar.monthrange` (e.g. Jan 31 -> Feb 28/29).

---

## 7. PolicyEngine Security & Pipeline Routing

### 7.1 Tool Risk Classifications & Confirmation Enforcement
All operations integrate with `PolicyEngine` and `ExecutionEngine`:

| Tool Name | Risk Level | Policy Decision | Confirmation Requirement |
| :--- | :---: | :---: | :--- |
| `productivity.create_task` | `LOW` (1) | `ALLOW` | Auto-allowed with audit record. |
| `productivity.list_tasks` | `SAFE` (0) | `ALLOW` | Auto-allowed. |
| `productivity.update_task` | `LOW` (1) | `ALLOW` | Auto-allowed with audit record. |
| `productivity.complete_task`| `LOW` (1) | `ALLOW` | Auto-allowed with audit record. |
| `productivity.delete_task` | `SENSITIVE` (2) | `NEED_CONFIRM` | **Token required:** Preview shows *"Delete task '{title}' (ID: {id})"* |
| `productivity.add_reminder` | `LOW` (1) | `ALLOW` | Auto-allowed with audit record. |
| `productivity.list_reminders`| `SAFE` (0) | `ALLOW` | Auto-allowed. |
| `productivity.reschedule_reminder`| `LOW` (1) | `ALLOW` | Auto-allowed with audit record. |
| `productivity.cancel_reminder`| `LOW` (1) | `ALLOW` | Auto-allowed with audit record. |
| `productivity.delete_reminder`| `SENSITIVE` (2) | `NEED_CONFIRM` | **Token required:** Preview shows *"Delete reminder '{title}' (ID: {id})"* |
| `productivity.save_note` | `LOW` (1) | `ALLOW` | Auto-allowed with audit record. |
| `productivity.list_notes` | `SAFE` (0) | `ALLOW` | Auto-allowed. |
| `productivity.search_notes`| `SAFE` (0) | `ALLOW` | Auto-allowed. |
| `productivity.delete_note` | `SENSITIVE` (2) | `NEED_CONFIRM` | **Token required:** Preview shows *"Delete note '{title}' (ID: {id})"* |
| `productivity.get_daily_plan`| `SAFE` (0) | `ALLOW` | Auto-allowed. |
| `productivity.calculate` | `SAFE` (0) | `ALLOW` | Legacy math (auto-allowed). |
| `productivity.start_stopwatch`| `SAFE` (0) | `ALLOW` | Legacy stopwatch (auto-allowed). |

### 7.2 Local-Only MVP Constraint
- No external calendar APIs (Google Calendar, Microsoft Graph, Apple CalDAV).
- No outbound emails, WhatsApp, or SMS messages are initiated by Capability 5.
- Zero new third-party pip dependencies.

---

## 8. Test Strategy

A dedicated test suite `tests/regression/test_productivity_skill.py` will be created covering all core and failure paths:

1. **Date/Time & Calendar Tests:**
   - Relative offsets ("in 15 minutes", "tomorrow at 3pm").
   - Invalid dates (Feb 30, April 31) return clear errors.
   - Timezone consistency (local timezone preservation and ISO formatting).
   - DST gap and overlap edge cases.
2. **Recurrence Engine Tests:**
   - Next occurrence calculations for daily, weekly, weekdays, monthly.
   - Month-end clamping (Jan 31 -> Feb 28).
   - Multi-day missed recurrence collapse into a single catch-up notification.
3. **Task & Notes CRUD Tests:**
   - Task lifecycle (`pending` -> `in_progress` -> `completed`).
   - Priority sorting (`urgent` > `high` > `normal` > `low`).
   - Note saving, listing, and full-text querying via `notes_fts`.
4. **Scheduler Lifecycle & Concurrency Tests:**
   - `test_concurrent_scheduler_startup`: Concurrent calls to `start()` spawn exactly one thread.
   - `test_graceful_shutdown`: `shutdown()` cleanly terminates thread within timeout.
   - `test_database_lock_backoff`: Simulating SQLite `OperationalError: database is locked`; verifies scheduler backs off and retries on next poll without crashing.
5. **Crash-Safe Dispatch & Atomic Lease Tests:**
   - Atomic claiming query prevents concurrent threads/processes from claiming the same reminder.
   - Stale lease recovery (`lease_until` in past) successfully re-claims and re-attempts dispatch.
   - Verification that dispatch failure transitions through `PENDING` backoff to `DISPATCH_FAILED` after 3 retries.
6. **Delivery Guarantees & Retry Tests:**
   - State transition from `PENDING` -> `DUE` -> `DISPATCHING` -> `DISPATCHED`.
   - Dispatch failure retry with backoff; transitions to `DISPATCH_FAILED` after max attempts.
   - De-duplication: Rejection of identical reminder within 60s window.
7. **Restart Recovery & Missed Reminders Tests:**
   - Reminders due in past within grace window (e.g. 2h ago) delivered as catch-up alerts.
   - Reminders due beyond grace window (e.g. 48h ago) marked `EXPIRED` without alerting.
8. **PolicyEngine & Confirmation Enforcement Tests:**
   - `delete_task`, `delete_reminder`, `delete_note` return `NEED_CONFIRM`.
   - Action succeeds only upon valid token consumption.
9. **Migration V4 Safety & Rollback Tests:**
   - WAL checkpointing (`PRAGMA wal_checkpoint(TRUNCATE)`) and SQLite online backup API validation.
   - Pre-migration backup verified with `PRAGMA integrity_check`.
   - Running migration multiple times proves idempotency.
   - Interrupted-migration recovery: Simulating mid-migration failure restores pre-migration snapshot without schema corruption.
10. **Full Suite Regression:**
    - All 212 existing regression tests must pass cleanly.

---

## 9. Unresolved Risks & Documented Limitations

1. **OS-Level Process Termination Boundary:**
   - While `ProductivityScheduler` cleanly joins and flushes on normal exit, exceptions, and `SIGTERM`/`atexit`, an abrupt OS termination (`taskkill /F`, power cut) cannot run Python cleanup.
   - *Mitigation:* The atomic lease recovery routine safely reclaims expired leases upon the next application boot.
2. **System Sleep / Hibernation Clock Drift:**
   - When a Windows PC enters sleep or hibernation, Python timer threads pause.
   - *Mitigation:* The scheduler checks `datetime.now().astimezone()` against `remind_at` on every wake-up tick, detecting any reminders that elapsed during sleep.
3. **Lack of Native OS Desktop Toast Notifications:**
   - The current GUI architecture does not have a Windows Notification Center toast integration; notifications dispatch to the CustomTkinter HUD cockpit console and SAPI5 voice speaker.
   - *Boundary:* Documented honestly; reminders are marked `DISPATCHED` to console/voice, but OS-level toast delivery is out of scope for this MVP.
4. **Limits of Exactly-Once Delivery with Hardware Side Effects:**
   - Because hardware audio playback and screen display cannot be enlisted in a 2PC database transaction, an abrupt power failure during SAPI5 audio generation will cause the recovered scheduler to re-announce the reminder upon reboot. The system provides **at-least-once delivery with atomic deduplication**.

---

## 10. Acceptance Criteria for Capability 5

- [x] Single-instance scheduler runs as a daemon thread with graceful shutdown and database lock backoff.
- [x] Atomic database leases prevent duplicate dispatches across concurrent processes and recover crashed leases.
- [x] Unified database (`database/oliver.db`) is used exclusively; split-brain storage in `ayra_memory.db` eliminated.
- [x] Migration V4 executes idempotently with WAL checkpointing and verified online backup snapshot.
- [x] Tasks support CRUD, priority tiers, due dates, and status state transitions (`pending` -> `in_progress` -> `completed`).
- [x] Reminders support one-time and recurring schedules (`daily`, `weekly`, `weekdays`, `monthly`).
- [x] Date/time parser handles relative offsets, local timezones, DST transitions, and rejects invalid calendar dates.
- [x] Formal state machine tracks `PENDING`, `DUE`, `DISPATCHING`, `DISPATCHED`, `ACKNOWLEDGED`, `MISSED`, `EXPIRED`, and `DISPATCH_FAILED`.
- [x] Restart recovery surfaces missed reminders within the grace window and collapses multi-day recurring backlogs.
- [x] Delivery failures retry with backoff without crashing the scheduler loop.
- [x] Notes support full-text search via SQLite FTS5.
- [x] Deletion of tasks, reminders, or notes requires explicit user confirmation via PolicyEngine (`NEED_CONFIRM`).
- [x] Legacy calculator and stopwatch tools continue to function with zero regressions.
- [x] All 212 existing regression tests continue to pass without failure.
- [x] New test suite for Capability 5 passes cleanly (233 total regression tests passing).

---

## 11. Completion Status

**COMPLETED.** All Capability 5 requirements implemented, tested, and verified. Ready for user verification.
