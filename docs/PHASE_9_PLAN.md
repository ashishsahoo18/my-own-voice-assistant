# OLIVER 2.0 — Phase 9 Technical Blueprint & Implementation Plan
# HUD / Desktop UI Overhaul & Windows AI Cockpit Hardening

**Date:** October 28, 2026  
**Status:** IMPLEMENTED & VERIFIED (Stages 9.1 – 9.7 Complete; 252/252 Tests Passing)  
**Target Branch:** `oliver-2.0`  
**Branding:** `OLIVER 2.0 — Windows AI Cockpit`  
**Subtitle:** `Autonomous Voice & Task Assistant`  
**Boundary:** Strictly local HUD/UI; zero Windows Toast / WinRT integration; zero paid/external cloud dependencies.

---

## 1. Executive Summary & Architectural Scope

Phase 9 modernizes and hardens the graphical user interface for OLIVER 2.0. The existing GUI (`ui/app.py`, `ui/chat.py`, `ui/setting.py`) runs on CustomTkinter and Tkinter. This phase resolves critical deficiencies in thread safety, truthful status reporting, policy confirmation handling, productivity reminder interactions, emergency stop controls, and shutdown resource management.

### Key Architectural Decisions
1. **Thread-Safe UI Bridge**: All Tkinter/CustomTkinter widget access is strictly confined to the main thread via a synchronized `UIEventQueue` polled on a 25ms interval. Background threads never invoke `root.after()` or widget methods across thread boundaries.
2. **Policy & Execution Integrity**: UI actions never bypass security policies or invoke tools directly. All commands and confirmed actions route through `IntentRouter` -> `PolicyEngine` -> `ConfirmationManager` -> `ExecutionEngine` -> `VerifierRegistry`.
3. **Local HUD Reminders**: Reminders are delivered into a local HUD card and drawer. No Windows Notification Center / WinRT Toast notifications are used.
4. **Emergency Stop (Kill Switch)**: A dedicated Cockpit Emergency Stop control activates `security/kill_switch.py`, immediately revoking tokens, blocking execution, and logging all active operations.
5. **Truthful Status Badges**: The HUD reflects true tool execution results (`VERIFIED`, `UNVERIFIED`, `FAILED`, `DENIED`, `CANCELLED`, `TIMEOUT`, `NEED_CONFIRM`) rather than inspecting plain return strings.
6. **Bounded Shutdown Protocol**: The shutdown sequence uses a target budget, bounded thread joins, and truthful logging. If a background worker does not stop before its deadline, UI teardown proceeds without claiming the worker terminated, and active database connections are preserved to avoid corruption.

---

## 2. Stage Breakdown & Acceptance Criteria

### Stage 9.1: Thread-Safe UI Event Bridge (`UIEventQueue`)
- **Objective**: Implement `ui/event_bridge.py` providing a thread-safe message queue.
- **Design**:
  - `UIEventQueue` encapsulates a standard thread-safe `queue.Queue`.
  - Background workers invoke `ui_bridge.post(callback, *args, **kwargs)` without touching Tkinter widgets.
  - Main thread schedules a recurring polling callback `root.after(25, self._poll_queue)`.
  - Closed bridge state (`_accepting = False`) discards events pushed during or after shutdown, logging drop counts.
- **Acceptance Criteria**:
  - 100 concurrent worker threads post events without throwing `TclError` or UI thread deadlocks.
  - Events posted after bridge shutdown return `False` and are discarded safely.

### Stage 9.2: Branding & Configuration Migration
- **Objective**: Update branding and migrate settings to `core/config.py`.
- **Design**:
  - Header displays: `OLIVER 2.0 — Windows AI Cockpit`.
  - Window title: `OLIVER 2.0 — Windows AI Cockpit`.
  - Migrate `ui/app.py` and `ui/setting.py` from legacy `AppSettings` to `core.config.get_config()`.
  - Preserve backward-compatible class aliases (`AyraApp = AshishApp`, `ChatPanel = CommandConsolePanel`).
- **Acceptance Criteria**:
  - Application displays official branding.
  - Configuration reads typed fields from `OliverConfig` with full backward compatibility.
  - User `.env` and configuration files are never modified automatically.

### Stage 9.3: Truthful Status Badges & Confirmation Modal
- **Objective**: Replace string heuristic matching with typed `ToolResult` status badges and connect `ConfirmationModal`.
- **Design**:
  - Expose `IntentRouter.execute_route_result()` returning typed `ToolResult`.
  - `CommandConsoleEntry` renders color-coded status badges:
    - `VERIFIED`: Emerald Green (#10B981)
    - `UNVERIFIED`: Amber (#F59E0B)
    - `FAILED`: Crimson (#EF4444)
    - `DENIED`: Red-Violet (#991B1B)
    - `CANCELLED`: Neutral Slate (#64748B)
    - `TIMEOUT`: Orange (#EA580C)
    - `NEED_CONFIRM`: Gold (#D97706)
  - When `NEED_CONFIRM` is returned, open modal displaying exact signed preview string. User confirmation submits `TaskRequest(confirmation_token=token)` via `ExecutionEngine`.
- **Acceptance Criteria**:
  - Risky actions (Risk 2/3) prompt modal with exact parameter preview.
  - Denials and confirmations faithfully update entry status badges.
  - Direct execution bypass is impossible from the UI layer.

### Stage 9.4: Emergency Stop & Hardware Telemetry
- **Objective**: Cockpit Emergency Stop and real-time audio hardware status pill.
- **Design**:
  - Add `[ EMERGENCY STOP ]` button to Left Panel.
  - Click invokes `kill_switch.activate()`, halts audio synthesis, revokes pending confirmation tokens, and locks input.
  - Reactivation requires an explicit safety confirmation modal before calling `kill_switch.deactivate()`.
  - Add microphone active/muted pill bound to `voice_manager.is_microphone_active`.
- **Acceptance Criteria**:
  - Emergency stop immediately prevents any new tool execution.
  - In-flight cancellations are audited truthfully; un-abortable tools are flagged as in-flight.
  - Reactivation cleanly restores normal cockpit operations.

### Stage 9.5: Multi-Step Agent Task Monitor
- **Objective**: Real-time progress monitor and task cancellation for multi-step autonomous loops.
- **Design**:
  - Render active task step, total steps, and current tool description in Center Stage.
  - Provide a responsive `[ CANCEL TASK ]` button hooked to `AgentTaskLoop.cancel()`.
- **Acceptance Criteria**:
  - Multi-step loops update step count and tool description via `UIEventQueue`.
  - Clicking cancel requests cooperative loop termination and marks task status `CANCELLED`.

### Stage 9.6: Productivity Reminder HUD Cards
- **Objective**: Interactive HUD reminder cards and drawer for `ProductivityService`.
- **Design**:
  - Connect reminder listener in `ProductivityService`.
  - Display interactive cards with `[ ACKNOWLEDGE ]` button.
  - Clicking `[ ACKNOWLEDGE ]` calls `service.acknowledge_reminder(reminder_id)`.
  - Keep `database/oliver.db` as the sole source of truth; never create duplicate storage.
  - State `DISPATCHED` is never treated as `ACKNOWLEDGED`.
- **Acceptance Criteria**:
  - Reminders pop up in local HUD drawer without touching Windows Toast.
  - Acknowledgment is idempotent and persists directly to SQLite.

---

### Stage 9.7: Bounded Shutdown Protocol & Resilient Resource Cleanup (CORRECTED)

#### 1. Scope, Guarantees, and Non-Guarantees
- **Target Budget**: 3.0 seconds is an aspirational shutdown target, not an unconditional guarantee.
- **Guaranteed Bounded Waiting**: The application guarantees bounded waiting for worker thread joins (up to per-worker timeouts) and bounded UI teardown where the CustomTkinter/Tkinter GUI framework permits.
- **Process Termination Non-Guarantee**: The application **does not guarantee that the entire Python process terminates within 3.5 seconds** if an arbitrary worker thread remains running, blocked on network/OS I/O, or unresponsive.
- **Distinct Teardown States**:
  - `UI_CLOSED`: The GUI event bridge has stopped accepting events, pending callbacks are drained/discarded, and the Tkinter window is destroyed. The GUI is off-screen.
  - `SHUTDOWN_CLEAN`: All registered worker threads acknowledged stop signals and joined within their timeouts. Background resources and SQLite connections closed cleanly.
  - `SHUTDOWN_INCOMPLETE`: One or more background worker threads exceeded their join deadlines and remain running. The UI is closed, but active workers remain alive in the background.
  - `PROCESS_TERMINATION`: The OS process exits. Neither thread detachment nor `sys.exit()` is treated as proof that an active worker has terminated.

#### 2. Database Ownership & Incomplete-Shutdown Handling
- **Connection Ownership**:
  - SQLite connections are managed by `UnifiedDatabase` via thread-local storage (`threading.local().conn`).
  - Each thread owns and uses its own isolated SQLite connection handle.
  - All write transactions require acquiring the internal threading mutex `_conn_lock`.
- **Preventing New Database Work at Shutdown**:
  - At the onset of shutdown, `UnifiedDatabase.set_accepting_transactions(False)` is engaged.
  - Any subsequent attempt to open a new transaction or acquire `_conn_lock` raises `ServiceShuttingDownError` and is rejected.
- **Active Connection Preservation on Worker Timeout**:
  - **Rule**: Never checkpoint or close a database connection that may still be in use by an active worker.
  - If any worker thread fails to join within its allotted deadline (`SHUTDOWN_INCOMPLETE`):
    - Do **not** execute `PRAGMA wal_checkpoint(PASSIVE)` on the shared database.
    - Do **not** close thread-local connection handles belonging to active worker threads.
    - Closing connections or freeing underlying C-level memory structures while an active thread is mid-query causes native segmentation faults or corrupt write frames.
- **SQLite WAL Resilience Limits**:
  - SQLite WAL mode is treated as a resilience mechanism against abrupt process termination, **not an unconditional guarantee against data corruption** (e.g. power failure during non-atomic OS buffer flush, hardware failure, or concurrent uncoordinated external writes).
  - Restart-time `PRAGMA integrity_check` and `PRAGMA quick_check` remain mandatory in `UnifiedDatabase` initialization to detect any anomalies.
  - Test suites must explicitly document that in-process unit tests cannot prove every real-world operating system crash scenario.

#### 3. Structured Shutdown Sequence
```
[WM_DELETE_WINDOW / Close Request]
              │
              ▼
[Step 1: Close UI Bridge]
  - UIEventQueue._accepting = False
  - Discard queued unrendered callbacks
  - Cancel UI polling timer
              │
              ▼
[Step 2: Signal Cancellation]
  - voice_manager.stop()
  - speaker.stop()
  - productivity_service.shutdown()
  - agent_loop.cancel()
  - db.set_accepting_transactions(False)
              │
              ▼
[Step 3: Bounded Thread Joins]
  - Voice threads (timeout=0.5s)
  - Scheduler thread (timeout=1.0s)
  - Agent task loop thread (timeout=1.0s)
              │
      ┌───────┴───────┐
      ▼               ▼
[All Joined]    [1+ Timed Out]
      │               │
      │               ▼
      │         Record TIMEOUT warning log
      │         Record worker thread identity
      │         Flag SHUTDOWN_INCOMPLETE
      │         Preserve open DB connections
      │               │
      ▼               │
[Step 4: DB Cleanup (Clean Only)] 
  - If Clean: PRAGMA wal_checkpoint(PASSIVE)
  - If Clean: Close DB connections
              │       │
              └───────┬───────┘
                      ▼
[Step 5: Window Teardown (UI_CLOSED)]
  - root.destroy()
  - Emit final ShutdownResult log
```

#### 4. Shutdown Acceptance Criteria
1. **Bounded Waiting**:
   - The shutdown routine returns and destroys the UI window within its bounded waiting budget (sum of worker timeouts + small grace period), even if a background worker is blocked.
2. **Truthful Outcome Logging**:
   - Timed-out workers are logged as `TIMEOUT (active)` and never reported as `STOPPED`.
   - The shutdown status is explicitly reported as `SHUTDOWN_INCOMPLETE` whenever any worker exceeds its join deadline.
3. **UI Event Bridge Rejection**:
   - Any worker thread attempting to post UI events after bridge closure receives `False`; events are discarded without touching widgets.
4. **No Destructive DB Action on Timeout**:
   - When a worker join times out, active database connections are left open to avoid corrupting active statements.
5. **Database Recovery Verification**:
   - Database remains verifiable via `PRAGMA quick_check` and `PRAGMA integrity_check` upon subsequent connection initialization.

#### 5. Automated Regression Test Specifications (`tests/regression/test_ui_pipeline.py`)
- **`test_shutdown_clean_order()`**:
  - Mock workers stopping cleanly within 50ms.
  - Verify sequence: UI bridge closed -> stop signaled -> workers joined -> DB checkpointed -> UI destroyed.
  - Verify result status is `SHUTDOWN_CLEAN`.
- **`test_shutdown_bounded_wait_on_hung_worker()`**:
  - Spawn a mock worker thread that blocks on an un-triggered event.
  - Execute shutdown with a 0.2s join timeout.
  - Verify shutdown completes in ~0.25s (bounded wait).
  - Assert status is `SHUTDOWN_INCOMPLETE`.
  - Assert the hung worker thread is listed in `timed_out_workers` and NOT in `joined_workers`.
  - Assert `db_checkpoint_executed` is `False`.
- **`test_event_bridge_rejection_after_shutdown()`**:
  - Close `UIEventQueue`.
  - Post callbacks from multiple threads.
  - Assert return value is `False`, queue remains empty, and widget mock is never called.
- **`test_sqlite_recovery_fresh_connection()`**:
  - Simulate transaction during abrupt shutdown.
  - Open a fresh connection in a separate context/process.
  - Execute `PRAGMA integrity_check` and `PRAGMA quick_check` to assert database consistency.

---

## 3. Rollback Plan & Pre-Implementation Safeguards

- Every stage is self-contained and independently testable via `tests/regression/test_ui_pipeline.py`.
- If regressions occur at any stage:
  - Revert the stage changes using Git restore.
  - All Phase 1–8 functionality, SQLite tables (`database/oliver.db`), and user files remain completely untouched.
- No files will be modified or created until explicit implementation approval is granted by the user.

---

## 4. Phase 9 Implementation Verification Summary

All Stages 9.1 through 9.7 are fully implemented and verified against the comprehensive regression suite:

1. **Stage 9.1 — Thread-Safe UI Event Bridge (`ui/event_bridge.py`)**:
   - `UIEventQueue` thread-safe queue with main-thread polling (`poll_interval_ms=25`).
   - Rejection and discarding of events after bridge closure.
   - Callback exception logging and isolation preventing UI loop crashes.

2. **Stage 9.2 — Configuration & Branding (`ui/app.py`, `ui/setting.py`, `core/config.py`)**:
   - Branding standardized to `OLIVER 2.0 — Windows AI Cockpit`.
   - Settings migrated to `OliverConfig` via `get_config()` with backward compatibility aliases.

3. **Stage 9.3 — Truthful Status Badges & Confirmation Modal Wiring (`security/confirmation.py`, `router/router.py`, `ai/assistant.py`, `ui/chat.py`)**:
   - `IntentRouter.execute_route_result()` and `AshishAssistant.handle_result()` returning typed `ToolResult`.
   - Badges mapped to truthful statuses (`VERIFIED`, `UNVERIFIED`, `FAILED`, `DENIED`, `CANCELLED`, `TIMEOUT`, `NEED_CONFIRM`).
   - Direct `ConfirmationModal` wiring with `invalidate_token()` on cancellation.

4. **Stage 9.4 — Kill Switch & Telemetry Indicators (`ui/app.py`, `ui/chat.py`, `security/kill_switch.py`)**:
   - Emergency Stop button in Left Panel activating `kill_switch.activate()`.
   - Modal confirmation required to reset kill switch.
   - Live hardware & system status telemetry (OLLAMA, VOICE, MIC PRIVACY, SCHEDULER, KILL SWITCH).

5. **Stage 9.5 — Multi-Step Agent Task Monitor & Cancellation (`agent/executor.py`, `ui/app.py`)**:
   - `AgentTaskLoop.run()` and `.resume()` report step progress via `on_progress` callback.
   - `AgentTaskMonitorCard` in Center Stage with progress bar, step label, and `[ CANCEL TASK ]` button.

6. **Stage 9.6 — Reminder Cards in HUD & Dispatch Wiring (`productivity/service.py`, `ui/app.py`)**:
   - Reminder dispatch listeners in `ProductivityService`.
   - `ReminderFeedPanel` and `ReminderItemCard` with idempotent acknowledgment updating SQLite directly.

7. **Stage 9.7 — Bounded Shutdown, Resource Cleanup & Database Integrity (`ui/app.py`, `memory/unified_db.py`, `tests/regression/test_ui_pipeline.py`)**:
   - Bounded teardown sequence in `AshishApp.destroy()`: closes bridge, cancels timers, stops audio, halts scheduler, invalidates tokens, and marks `UI_CLOSED` / `SHUTDOWN_INCOMPLETE`.
   - Preserves thread-local DB connections for active workers.
   - `UnifiedDatabase.check_integrity(quick=True/False)` PRAGMA check API.
   - Full regression suite passing: 252 tests.
