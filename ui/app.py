"""Main desktop shell for OLIVER 2.0 — Windows AI Cockpit."""

from __future__ import annotations

import math
import os
import threading
from datetime import datetime
from typing import Any, Callable, Optional
import customtkinter as ctk

try:
    import psutil
except ImportError:
    psutil = None

from ai.assistant import AshishAssistant
from config.settings import AppSettings
from core.config import OliverConfig, get_config
from database.chat_db import ChatStore
from ui.chat import CommandConsolePanel
from ui.event_bridge import UIEventQueue
from ui.setting import VoiceSettingsWindow
from voice.voice_manager import VoiceManager


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ConfirmationModal(ctk.CTkToplevel):
    """Modal dialog for dangerous commands, WhatsApp, and Email confirmation."""

    def __init__(
        self,
        parent: ctk.CTk,
        title: str,
        message: str,
        on_confirm,
        on_cancel,
        confirm_text: str = "CONFIRM",
        accent_color: str = "#ff3b30",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("520x280")
        self.resizable(False, False)
        self.configure(fg_color="#080e1e")

        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self._handled = False

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header with icon and title
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text=f"⚠️ {title.upper()}",
            font=("Segoe UI", 14, "bold"),
            text_color=accent_color,
        ).pack(anchor="w")

        # Message container
        msg_frame = ctk.CTkFrame(
            self,
            fg_color="#0d182e",
            corner_radius=10,
            border_width=1,
            border_color="#1d2e4a",
        )
        msg_frame.grid(row=1, column=0, padx=24, pady=10, sticky="nsew")

        ctk.CTkLabel(
            msg_frame,
            text=message,
            font=("Segoe UI", 12),
            text_color="#ffffff",
            wraplength=450,
            justify="left",
            anchor="w",
        ).pack(padx=14, pady=12, fill="both", expand=True)

        # Action buttons
        button_bar = ctk.CTkFrame(self, fg_color="transparent")
        button_bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 20))
        button_bar.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            button_bar,
            text="CANCEL",
            height=42,
            corner_radius=10,
            fg_color="#1a263b",
            hover_color="#2c3b57",
            border_width=1,
            border_color="#3a4d70",
            font=("Segoe UI", 12, "bold"),
            command=self._cancel,
        ).grid(row=0, column=0, padx=(0, 8), sticky="ew")

        ctk.CTkButton(
            button_bar,
            text=confirm_text,
            height=42,
            corner_radius=10,
            fg_color=accent_color,
            hover_color="#33ddff" if accent_color == "#00d2ff" else "#20b858",
            font=("Segoe UI", 12, "bold"),
            command=self._confirm,
        ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def _confirm(self) -> None:
        if self._handled:
            return
        self._handled = True
        self.destroy()
        if self.on_confirm:
            self.on_confirm()

    def _cancel(self) -> None:
        if self._handled:
            return
        self._handled = True
        self.destroy()
        if self.on_cancel:
            self.on_cancel()


class AgentTaskMonitorCard(ctk.CTkFrame):
    """Cockpit HUD card monitoring live multi-step agent planning and execution."""

    def __init__(self, parent: ctk.CTkFrame, on_cancel: Optional[Callable[[str], None]] = None) -> None:
        super().__init__(
            parent,
            fg_color="#091224",
            corner_radius=16,
            border_width=1,
            border_color="#152747",
        )
        self.on_cancel = on_cancel
        self.active_task_id: Optional[str] = None

        # Header row: Title + Status Pill
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            header,
            text="🎯 AGENT TASK MONITOR",
            font=("Segoe UI", 11, "bold"),
            text_color="#00d2ff",
            anchor="w",
        ).pack(side="left")

        self.status_badge = ctk.CTkLabel(
            header,
            text="IDLE",
            font=("Segoe UI", 10, "bold"),
            text_color="#64748b",
        )
        self.status_badge.pack(side="right")

        # Goal label
        self.goal_label = ctk.CTkLabel(
            self,
            text="Goal: Standby (No active agent task)",
            font=("Segoe UI", 11, "bold"),
            text_color="#ffffff",
            anchor="w",
            wraplength=340,
            justify="left",
        )
        self.goal_label.pack(fill="x", padx=16, pady=(0, 4))

        # Current step details
        self.step_label = ctk.CTkLabel(
            self,
            text="Step: -- / -- • Tool: None",
            font=("Segoe UI", 10),
            text_color="#8da5cc",
            anchor="w",
        )
        self.step_label.pack(fill="x", padx=16, pady=(0, 6))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=8,
            corner_radius=4,
            fg_color="#101c33",
            progress_color="#00d2ff",
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 10))

        # Cancel button
        self.cancel_btn = ctk.CTkButton(
            self,
            text="⏹  CANCEL TASK",
            height=32,
            corner_radius=8,
            fg_color="#334155",
            hover_color="#475569",
            text_color="#94a3b8",
            font=("Segoe UI", 10, "bold"),
            state="disabled",
            command=self._handle_cancel_click,
        )
        self.cancel_btn.pack(fill="x", padx=16, pady=(0, 12))

    def update_progress(
        self,
        task_id: str,
        step: int,
        total_steps: int,
        tool_name: str,
        description: str,
        status: str,
    ) -> None:
        """Update monitor card state with truthful progress data."""
        self.active_task_id = task_id
        normalized_status = status.upper()

        badge_colors = {
            "PLANNING": ("PLANNING", "#00d2ff"),
            "EXECUTING_STEP": ("EXECUTING", "#38f7a6"),
            "WAITING_FOR_CONFIRMATION": ("NEED CONFIRM", "#f59e0b"),
            "COMPLETED": ("COMPLETED", "#10b981"),
            "FAILED": ("FAILED", "#ef4444"),
            "CANCELLED": ("CANCELLED", "#64748b"),
        }
        badge_text, badge_color = badge_colors.get(normalized_status, (normalized_status, "#8da5cc"))
        try:
            self.status_badge.configure(text=badge_text, text_color=badge_color)

            if total_steps > 0:
                pct = min(1.0, max(0.0, step / float(total_steps)))
                self.progress_bar.set(pct)
                self.step_label.configure(
                    text=f"Step {step}/{total_steps} • Tool: {tool_name} ({description[:40]})"
                )
            else:
                self.progress_bar.set(0.0)
                self.step_label.configure(text=f"Tool: {tool_name} • {description[:40]}")

            if normalized_status in ("PLANNING", "EXECUTING_STEP", "WAITING_FOR_CONFIRMATION"):
                self.cancel_btn.configure(
                    state="normal",
                    fg_color="#7f1d1d",
                    hover_color="#991b1b",
                    text_color="#ffffff",
                )
            else:
                self.cancel_btn.configure(
                    state="disabled",
                    fg_color="#334155",
                    hover_color="#475569",
                    text_color="#94a3b8",
                )
        except Exception:
            pass

    def set_goal(self, goal: str) -> None:
        try:
            self.goal_label.configure(text=f"Goal: {goal}")
        except Exception:
            pass

    def _handle_cancel_click(self) -> None:
        if self.active_task_id and self.on_cancel:
            self.on_cancel(self.active_task_id)


class ReminderItemCard(ctk.CTkFrame):
    """Interactive card representing a single reminder in the HUD."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        reminder: Any,
        on_acknowledge: Optional[Callable[[int], None]] = None,
    ) -> None:
        st_val = getattr(reminder.status, "value", str(reminder.status)).upper() if hasattr(reminder, "status") else "PENDING"
        is_dispatched = st_val == "DISPATCHED"
        border_col = "#D97706" if is_dispatched else "#1d2e4a"
        bg_col = "#131f38" if is_dispatched else "#0a1324"

        super().__init__(
            parent,
            fg_color=bg_col,
            corner_radius=12,
            border_width=1,
            border_color=border_col,
        )
        self.pack(fill="x", padx=10, pady=4)
        self.reminder = reminder
        self.on_acknowledge = on_acknowledge

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(6, 2))

        title_text = getattr(reminder, "title", "Reminder")
        ctk.CTkLabel(
            header,
            text=f"⏰ {title_text}",
            font=("Segoe UI", 11, "bold"),
            text_color="#ffffff",
            anchor="w",
        ).pack(side="left")

        st_color = "#f59e0b" if is_dispatched else ("#10b981" if st_val in ("ACKNOWLEDGED", "COMPLETED") else "#64748b")

        self.status_lbl = ctk.CTkLabel(
            header,
            text=st_val,
            font=("Segoe UI", 9, "bold"),
            text_color=st_color,
        )
        self.status_lbl.pack(side="right")

        # Time row + Acknowledge Button
        bottom_row = ctk.CTkFrame(self, fg_color="transparent")
        bottom_row.pack(fill="x", padx=12, pady=(2, 6))

        remind_at = getattr(reminder, "remind_at", "") or ""
        time_str = remind_at[:16].replace("T", " ") if remind_at else "--"
        recurrence = getattr(reminder, "recurrence_rule", None)
        recur_str = f" • 🔁 {recurrence}" if recurrence else ""

        ctk.CTkLabel(
            bottom_row,
            text=f"{time_str}{recur_str}",
            font=("Segoe UI", 9),
            text_color="#8da5cc",
            anchor="w",
        ).pack(side="left")

        self.ack_btn = ctk.CTkButton(
            bottom_row,
            text="ACKNOWLEDGE",
            height=26,
            width=90,
            corner_radius=6,
            font=("Segoe UI", 9, "bold"),
            fg_color="#065f46" if is_dispatched else "#1e293b",
            hover_color="#047857" if is_dispatched else "#334155",
            text_color="#ffffff",
            command=self._handle_ack,
        )
        self.ack_btn.pack(side="right")

    def _handle_ack(self) -> None:
        self.ack_btn.configure(state="disabled", text="ACKNOWLEDGED", fg_color="#1e293b", text_color="#64748b")
        self.status_lbl.configure(text="ACKNOWLEDGED", text_color="#10b981")
        if self.on_acknowledge:
            rem_id = getattr(self.reminder, "id", None)
            if rem_id is not None:
                self.on_acknowledge(rem_id)


class ReminderFeedPanel(ctk.CTkFrame):
    """HUD drawer displaying active, due, and dispatched reminders."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        productivity_service: Optional[Any] = None,
        event_bridge: Optional[UIEventQueue] = None,
    ) -> None:
        super().__init__(
            parent,
            fg_color="#080e1e",
            corner_radius=16,
            border_width=1,
            border_color="#152747",
        )
        self.service = productivity_service
        self.event_bridge = event_bridge
        self._cards: dict[int, ReminderItemCard] = {}

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            header,
            text="🔔 HUD REMINDERS",
            font=("Segoe UI", 11, "bold"),
            text_color="#00d2ff",
            anchor="w",
        ).pack(side="left")

        # Scrollable container for reminder cards
        self.container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            height=120,
        )
        self.container.pack(fill="both", expand=True, padx=4, pady=4)

        if self.service:
            try:
                self.service.add_dispatch_listener(self._on_reminder_dispatched)
            except Exception:
                pass
            self.refresh_reminders()

    def _on_reminder_dispatched(self, reminder: Any) -> None:
        """Called from scheduler background thread: dispatches to UI main thread via bridge."""
        if self.event_bridge:
            self.event_bridge.post(self.handle_dispatched_reminder, reminder)
        else:
            self.handle_dispatched_reminder(reminder)

    def handle_dispatched_reminder(self, reminder: Any) -> None:
        """Update or add dispatched reminder card on main thread."""
        self.refresh_reminders()

    def refresh_reminders(self) -> None:
        """Reload pending and dispatched reminders from ProductivityService."""
        if not self.service:
            return
        try:
            reminders = self.service.list_reminders()
        except Exception:
            return

        for child in self.container.winfo_children():
            child.destroy()
        self._cards.clear()

        active_items = [
            r for r in reminders
            if getattr(r.status, "value", str(r.status)).upper() in ("PENDING", "DISPATCHED")
        ][:5]

        if not active_items:
            ctk.CTkLabel(
                self.container,
                text="No upcoming reminders scheduled.",
                font=("Segoe UI", 10),
                text_color="#516d99",
            ).pack(pady=12)
            return

        for r in active_items:
            card = ReminderItemCard(
                self.container,
                reminder=r,
                on_acknowledge=self.acknowledge_reminder,
            )
            rem_id = getattr(r, "id", None)
            if rem_id is not None:
                self._cards[rem_id] = card

    def acknowledge_reminder(self, reminder_id: int) -> None:
        """Idempotently acknowledge a reminder via ProductivityService."""
        if self.service:
            try:
                self.service.acknowledge_reminder(reminder_id)
            except Exception:
                pass


class AshishApp(ctk.CTk):
    """Futuristic ASHISH AI Desktop Assistant Application Shell."""

    def __init__(self, config: Optional[OliverConfig] = None) -> None:
        super().__init__()

        self.config: OliverConfig = config or get_config()
        self.settings = self.config  # Preserved for backward compatibility

        self.title("OLIVER 2.0 — Windows AI Cockpit")
        self.geometry("1480x880")
        self.minsize(1200, 750)

        self.assistant = AshishAssistant()
        self.store = ChatStore()
        self.voice_manager = VoiceManager()

        self.status_var = ctk.StringVar(value="SYSTEM ONLINE")
        self.ai_state_var = ctk.StringVar(value="READY")
        self.theme_var = ctk.StringVar(value="Dark Mode")

        self.current_state = "READY"

        self._orb_job = None
        self._monitor_job = None
        self._is_destroyed = False
        self._telemetry_counter = 0
        self._telemetry_in_flight = False

        self.event_bridge = UIEventQueue()
        self.event_bridge.bind_root(self)
        self.event_bridge.start_polling()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._configure_window()
        self._build_layout()
        self._start_system_monitoring()
        self._start_orb_animation()

    def _configure_window(self) -> None:
        self.configure(fg_color="#030712")

        # 3-column futuristic layout: Left Monitor (310px), Center Orb (flex), Right Console (450px)
        self.grid_columnconfigure(0, minsize=310, weight=0)
        self.grid_columnconfigure(1, minsize=420, weight=1)
        self.grid_columnconfigure(2, minsize=450, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _build_layout(self) -> None:
        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        """Left System Monitor Panel."""
        self.left_panel = ctk.CTkFrame(
            self,
            fg_color="#060c19",
            corner_radius=0,
            border_width=1,
            border_color="#101c33",
        )
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(22, 16))

        title = ctk.CTkLabel(
            header,
            text="OLIVER 2.0",
            font=("Segoe UI", 30, "bold"),
            text_color="#00d2ff",
            anchor="w",
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header,
            text="Windows AI Cockpit",
            font=("Segoe UI", 12),
            text_color="#6282b3",
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        status_indicator = ctk.CTkLabel(
            header,
            textvariable=self.status_var,
            font=("Segoe UI", 12, "bold"),
            text_color="#00ff9d",
            anchor="w",
        )
        status_indicator.pack(anchor="w", pady=(14, 0))

        # Real Live System Monitor Dashboard Card
        self._build_system_monitor_card()

        # Navigation / Action controls
        bottom = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=18)

        self.kill_switch_btn = ctk.CTkButton(
            bottom,
            text="🚨  EMERGENCY STOP",
            height=44,
            corner_radius=12,
            fg_color="#7F1D1D",
            hover_color="#991B1B",
            border_width=1,
            border_color="#B91C1C",
            font=("Segoe UI", 12, "bold"),
            text_color="#FFFFFF",
            command=self.toggle_kill_switch,
        )
        self.kill_switch_btn.pack(fill="x", pady=(0, 10))

        settings_btn = ctk.CTkButton(
            bottom,
            text="⚙️  SETTINGS",
            height=44,
            corner_radius=12,
            fg_color="#0b172d",
            hover_color="#16294a",
            border_width=1,
            border_color="#1f3863",
            font=("Segoe UI", 12, "bold"),
            text_color="#00d2ff",
            command=self.open_voice_settings,
        )
        settings_btn.pack(fill="x")

    def _build_system_monitor_card(self) -> None:
        """Build System Monitor Card with real psutil updates and truthful telemetry pills."""
        card = ctk.CTkFrame(
            self.left_panel,
            fg_color="#091224",
            corner_radius=18,
            border_width=1,
            border_color="#152747",
        )
        card.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkLabel(
            card,
            text="SYSTEM MONITOR",
            font=("Segoe UI", 12, "bold"),
            text_color="#00d2ff",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 10))

        metrics = [
            ("CPU", "0%"),
            ("RAM", "0%"),
            ("BATTERY", "Checking"),
            ("NETWORK", "ONLINE"),
            ("OLLAMA", "CHECKING"),
            ("VOICE", "READY"),
            ("MIC PRIVACY", "MIC: CLOSED"),
            ("SCHEDULER", "CHECKING"),
            ("KILL SWITCH", "STANDBY"),
            ("TIME", "--:--"),
            ("DATE", "--"),
        ]

        self.metric_labels: dict[str, ctk.CTkLabel] = {}

        for label, default_val in metrics:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=4)

            ctk.CTkLabel(
                row,
                text=label,
                font=("Segoe UI", 10, "bold"),
                text_color="#718bb5",
                anchor="w",
            ).pack(side="left")

            val_label = ctk.CTkLabel(
                row,
                text=default_val,
                font=("Segoe UI", 11, "bold"),
                text_color="#ffffff",
                anchor="e",
            )
            val_label.pack(side="right")

            self.metric_labels[label] = val_label

    def _build_center_panel(self) -> None:
        """Center AI Orb and State Display."""
        self.center_panel = ctk.CTkFrame(
            self,
            fg_color="#040914",
            corner_radius=0,
            border_width=1,
            border_color="#0b172a",
        )
        self.center_panel.grid(row=0, column=1, sticky="nsew")
        self.center_panel.grid_columnconfigure(0, weight=1)
        self.center_panel.grid_rowconfigure(2, weight=1)

        # Title Header
        ctk.CTkLabel(
            self.center_panel,
            text="OLIVER 2.0",
            font=("Segoe UI", 36, "bold"),
            text_color="#ffffff",
        ).grid(row=0, column=0, pady=(40, 2))

        ctk.CTkLabel(
            self.center_panel,
            text="WINDOWS AI COCKPIT",
            font=("Segoe UI", 11, "bold"),
            text_color="#00d2ff"
        ).grid(row=1, column=0)

        # Orb canvas wrapper
        orb_wrap = ctk.CTkFrame(
            self.center_panel,
            fg_color="transparent",
        )
        orb_wrap.grid(row=2, column=0, sticky="nsew", padx=20, pady=20)
        orb_wrap.grid_columnconfigure(0, weight=1)
        orb_wrap.grid_rowconfigure(0, weight=1)

        self.orb_canvas = ctk.CTkCanvas(
            orb_wrap,
            width=380,
            height=380,
            bg="#040914",
            highlightthickness=0,
        )
        self.orb_canvas.grid(row=0, column=0)

        self._orb_phase = 0.0

        # State Indicator
        self.state_label = ctk.CTkLabel(
            self.center_panel,
            textvariable=self.ai_state_var,
            font=("Segoe UI", 22, "bold"),
            text_color="#00d2ff",
        )
        self.state_label.grid(row=3, column=0, pady=(0, 6))

        ctk.CTkLabel(
            self.center_panel,
            text="Speak or type a command to execute",
            font=("Segoe UI", 12),
            text_color="#516d99",
        ).grid(row=4, column=0, pady=(0, 16))

        # Agent Task Monitor Card
        self.agent_monitor = AgentTaskMonitorCard(
            self.center_panel,
            on_cancel=self.cancel_agent_task,
        )
        self.agent_monitor.grid(row=5, column=0, padx=24, pady=(0, 10), sticky="ew")

        # HUD Reminder Feed Drawer
        try:
            from productivity.service import get_productivity_service
            prod_srv = get_productivity_service()
        except Exception:
            prod_srv = None

        self.reminder_feed = ReminderFeedPanel(
            self.center_panel,
            productivity_service=prod_srv,
            event_bridge=self.event_bridge,
        )
        self.reminder_feed.grid(row=6, column=0, padx=24, pady=(0, 20), sticky="ew")

    def cancel_agent_task(self, task_id: str) -> None:
        """Cancel active agent task and update UI."""
        from agent.executor import get_agent_task_loop
        get_agent_task_loop().cancel(task_id)
        if hasattr(self, "agent_monitor"):
            self.agent_monitor.update_progress(
                task_id=task_id,
                step=0,
                total_steps=0,
                tool_name="system",
                description="Task cancelled by user",
                status="cancelled",
            )
        if hasattr(self, "console_panel") and self.console_panel:
            self.console_panel._log_console_entry(
                f"cancel task {task_id}",
                "AGENT",
                f"Agent task '{task_id}' cancelled by user.",
                "CANCELLED",
                None,
            )

    def _build_right_panel(self) -> None:
        """Right Command Console Panel."""
        self.right_panel = ctk.CTkFrame(
            self,
            fg_color="#050a17",
            corner_radius=0,
            border_width=1,
            border_color="#101c33",
        )
        self.right_panel.grid(row=0, column=2, sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(0, weight=1)

        self.console_panel = CommandConsolePanel(
            self.right_panel,
            self.assistant,
            self.store,
            self.voice_manager,
            on_state_change=self.set_state,
            request_confirmation=self.show_confirmation_modal,
            event_bridge=self.event_bridge,
        )
        self.console_panel.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

    def set_state(self, state: str) -> None:
        """Update active AI orb state."""
        self.current_state = state
        self.ai_state_var.set(state.upper())
        if state == "READY":
            self.state_label.configure(text_color="#00d2ff")
        elif state == "LISTENING":
            self.state_label.configure(text_color="#00ff9d")
        elif state == "PROCESSING":
            self.state_label.configure(text_color="#ffcf36")
        elif state == "EXECUTING":
            self.state_label.configure(text_color="#ff36e8")
        elif state == "SPEAKING":
            self.state_label.configure(text_color="#36b6ff")
        elif state == "ERROR":
            self.state_label.configure(text_color="#ff4444")
        elif state in ("KILLED", "ENGAGED"):
            self.state_label.configure(text_color="#ef4444")

    def show_confirmation_modal(
        self,
        title: str = "OLIVER 2.0 Confirmation",
        message: str = "",
        on_confirm = None,
        on_cancel = None,
        confirm_text: str = "CONFIRM",
        accent_color: str = "#ff3b30",
    ) -> None:
        """Show dynamic command confirmation modal dialog."""
        ConfirmationModal(
            self,
            title=title,
            message=message,
            on_confirm=on_confirm,
            on_cancel=on_cancel,
            confirm_text=confirm_text,
            accent_color=accent_color,
        )

    def _start_orb_animation(self) -> None:
        """Animate multi-ring glowing futuristic ASHISH AI Orb."""
        self.orb_canvas.delete("all")

        size = 380
        cx, cy = size // 2, size // 2
        self._orb_phase += 0.08
        phase = self._orb_phase

        state = self.current_state

        # State pulse modifier
        if state == "LISTENING":
            pulse_r = math.sin(phase * 2.5) * 12
            color_outer = "#00ff9d"
            color_mid = "#00c473"
        elif state == "PROCESSING":
            pulse_r = math.sin(phase * 4.0) * 8
            color_outer = "#ffcf36"
            color_mid = "#e6b000"
        elif state == "EXECUTING":
            pulse_r = math.sin(phase * 5.0) * 16
            color_outer = "#ff36e8"
            color_mid = "#b800a3"
        elif state == "SPEAKING":
            pulse_r = math.sin(phase * 3.0) * 10
            color_outer = "#36b6ff"
            color_mid = "#0088cc"
        elif state in ("KILLED", "ENGAGED"):
            pulse_r = math.sin(phase * 1.5) * 6
            color_outer = "#ef4444"
            color_mid = "#7f1d1d"
        elif state == "ERROR":
            pulse_r = math.sin(phase * 6.0) * 14
            color_outer = "#ff4444"
            color_mid = "#cc0000"
        else:  # READY
            pulse_r = math.sin(phase) * 6
            color_outer = "#00d2ff"
            color_mid = "#0077b6"

        # Outer energy ring
        r_outer = 145 + pulse_r
        self.orb_canvas.create_oval(
            cx - r_outer,
            cy - r_outer,
            cx + r_outer,
            cy + r_outer,
            outline=color_outer,
            width=2,
        )

        # Concentric rotating HUD arcs
        for i in range(3):
            arc_r = 125 - i * 15
            start_angle = (phase * 40 * (i + 1)) % 360
            self.orb_canvas.create_arc(
                cx - arc_r,
                cy - arc_r,
                cx + arc_r,
                cy + arc_r,
                start=start_angle,
                extent=80,
                style="arc",
                outline=color_mid,
                width=3,
            )

        # Core glowing orb
        r_core = 75 + pulse_r * 0.4
        self.orb_canvas.create_oval(
            cx - r_core,
            cy - r_core,
            cx + r_core,
            cy + r_core,
            fill="#051833",
            outline=color_outer,
            width=3,
        )

        # Inner highlight
        r_inner = 35 + pulse_r * 0.2
        self.orb_canvas.create_oval(
            cx - r_inner,
            cy - r_inner,
            cx + r_inner,
            cy + r_inner,
            fill=color_outer,
            outline="#ffffff",
            width=2,
        )

        # Text label inside core
        self.orb_canvas.create_text(
            cx,
            cy,
            text="OLIVER",
            fill="#ffffff",
            font=("Segoe UI", 16, "bold"),
        )

        if self.__dict__.get("_is_destroyed", False):
            return
        self._orb_job = self.after(50, self._start_orb_animation)

    def _start_system_monitoring(self) -> None:
        """Poll real live system metrics via psutil."""
        try:
            if psutil:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                battery = psutil.sensors_battery()

                self.metric_labels["CPU"].configure(text=f"{cpu:.0f}%")
                self.metric_labels["RAM"].configure(text=f"{ram:.0f}%")

                if battery:
                    b_str = f"{battery.percent:.0f}% {'⚡' if battery.power_plugged else ''}"
                    self.metric_labels["BATTERY"].configure(text=b_str)
                else:
                    self.metric_labels["BATTERY"].configure(text="AC Power")
        except Exception:
            pass

        now = datetime.now()
        if "TIME" in self.metric_labels:
            self.metric_labels["TIME"].configure(text=now.strftime("%I:%M %p"))
        if "DATE" in self.metric_labels:
            self.metric_labels["DATE"].configure(text=now.strftime("%b %d, %Y"))

        self._telemetry_counter += 1
        if self._telemetry_counter % 3 == 0 and not self._telemetry_in_flight:
            self._telemetry_in_flight = True
            threading.Thread(target=self._run_telemetry_probe, daemon=True).start()

        if self.__dict__.get("_is_destroyed", False):
            return
        self._monitor_job = self.after(1000, self._start_system_monitoring)

    def _run_telemetry_probe(self) -> None:
        try:
            self._poll_telemetry_background()
        finally:
            self._telemetry_in_flight = False

    def _poll_telemetry_background(self) -> None:
        """Poll truthful status of Ollama, Voice, Mic, Scheduler, and Kill Switch in worker thread."""
        try:
            # 1. Ollama AI status
            ollama_status = "OFFLINE"
            ollama_color = "#EF4444"
            if hasattr(self.assistant, "ai_service"):
                is_healthy, _, _, _, _ = self.assistant.ai_service.check_health()
                if is_healthy:
                    ollama_status = "READY"
                    ollama_color = "#10B981"

            # 2. Voice state
            voice_state = "IDLE"
            voice_color = "#00D2FF"
            if hasattr(self.voice_manager, "current_state"):
                st = getattr(self.voice_manager.current_state, "value", str(self.voice_manager.current_state))
                voice_state = str(st).upper()
                if voice_state == "LISTENING":
                    voice_color = "#10B981"
                elif voice_state == "SPEAKING":
                    voice_color = "#A855F7"
                elif voice_state == "MUTED":
                    voice_color = "#64748B"

            # 3. Microphone hardware capture privacy
            mic_status = "MIC: CLOSED"
            mic_color = "#64748B"
            if hasattr(self.voice_manager, "is_microphone_active") and self.voice_manager.is_microphone_active:
                mic_status = "MIC: ACTIVE"
                mic_color = "#10B981"

            # 4. Scheduler health
            sched_status = "OK"
            sched_color = "#10B981"
            try:
                from productivity.service import get_productivity_service
                prod_srv = get_productivity_service()
                if hasattr(prod_srv, "scheduler") and not prod_srv.scheduler.is_running():
                    sched_status = "PAUSED"
                    sched_color = "#F59E0B"
            except Exception:
                sched_status = "N/A"
                sched_color = "#64748B"

            # 5. Kill switch state
            from security.kill_switch import get_kill_switch
            ks_active = get_kill_switch().is_active
            ks_status = "ENGAGED" if ks_active else "STANDBY"
            ks_color = "#EF4444" if ks_active else "#10B981"

            telemetry_data = {
                "OLLAMA": (ollama_status, ollama_color),
                "VOICE": (voice_state, voice_color),
                "MIC PRIVACY": (mic_status, mic_color),
                "SCHEDULER": (sched_status, sched_color),
                "KILL SWITCH": (ks_status, ks_color),
            }

            self.event_bridge.post(self._apply_telemetry_updates, telemetry_data)
        except Exception:
            pass

    def _apply_telemetry_updates(self, telemetry_data: dict[str, tuple[str, str]]) -> None:
        if self.__dict__.get("_is_destroyed", False):
            return
        for key, (text_val, color_val) in telemetry_data.items():
            lbl = self.metric_labels.get(key)
            if lbl:
                try:
                    lbl.configure(text=text_val, text_color=color_val)
                except Exception:
                    pass

    def toggle_kill_switch(self) -> None:
        """Toggle emergency kill switch: immediate activation or modal-confirmed reset."""
        from security.kill_switch import get_kill_switch
        ks = get_kill_switch()
        if not ks.is_active:
            ks.activate(reason="User clicked Emergency Stop in Cockpit UI")
            self.voice_manager.barge_in()
            self.set_state("KILLED")
            self._update_kill_switch_ui(True)
            if hasattr(self, "console_panel") and self.console_panel:
                self.console_panel.handle_kill_switch_activated()
        else:
            self.show_confirmation_modal(
                title="Safety Reset Confirmation",
                message="Are you sure you want to disengage the emergency kill switch and restore normal operations?",
                on_confirm=self._confirm_kill_switch_reset,
                confirm_text="RESET SWITCH",
                accent_color="#F59E0B",
            )

    def _confirm_kill_switch_reset(self) -> None:
        from security.kill_switch import get_kill_switch
        ks = get_kill_switch()
        ks.deactivate()
        self.set_state("READY")
        self._update_kill_switch_ui(False)
        if hasattr(self, "console_panel") and self.console_panel:
            self.console_panel.handle_kill_switch_deactivated()

    def _update_kill_switch_ui(self, is_active: bool) -> None:
        if not hasattr(self, "kill_switch_btn") or not self.kill_switch_btn:
            return
        try:
            if is_active:
                self.kill_switch_btn.configure(
                    text="⚠️  RESET KILL SWITCH",
                    fg_color="#D97706",
                    hover_color="#B45309",
                    border_color="#F59E0B",
                    text_color="#000000",
                )
            else:
                self.kill_switch_btn.configure(
                    text="🚨  EMERGENCY STOP",
                    fg_color="#7F1D1D",
                    hover_color="#991B1B",
                    border_color="#B91C1C",
                    text_color="#FFFFFF",
                )
        except Exception:
            pass

    def open_voice_settings(self) -> None:
        VoiceSettingsWindow(self.voice_manager, config=self.config)

    def _on_close(self) -> None:
        """Safe window closure: shutdown bridge first, cancel timers, then destroy widgets."""
        self.destroy()

    def destroy(self) -> None:
        """Ensure bounded, orderly shutdown before widget hierarchy is torn down (idempotent)."""
        if self.__dict__.get("_is_destroyed", False):
            return
        self._is_destroyed = True

        shutdown_status = "UI_CLOSED"
        incomplete_reasons: list[str] = []

        # 1. Stop accepting new events and drain pending events
        event_bridge = self.__dict__.get("event_bridge")
        if event_bridge is not None:
            try:
                event_bridge.shutdown()
            except Exception as exc:
                incomplete_reasons.append(f"event_bridge: {exc}")

        # 2. Cancel all recurring Tkinter timers immediately
        orb_job = self.__dict__.get("_orb_job")
        if orb_job is not None:
            try:
                self.after_cancel(orb_job)
            except Exception:
                pass
            self._orb_job = None

        monitor_job = self.__dict__.get("_monitor_job")
        if monitor_job is not None:
            try:
                self.after_cancel(monitor_job)
            except Exception:
                pass
            self._monitor_job = None

        # 3. Halt speech and audio capture
        voice_manager = self.__dict__.get("voice_manager")
        if voice_manager is not None:
            try:
                voice_manager.barge_in()
            except Exception as exc:
                incomplete_reasons.append(f"voice_manager: {exc}")

        # 4. Stop productivity scheduler daemon with bounded timeout (1.0s target)
        try:
            from productivity.service import get_productivity_service
            prod_srv = get_productivity_service()
            if prod_srv and hasattr(prod_srv, "shutdown"):
                prod_srv.shutdown()
        except Exception as exc:
            incomplete_reasons.append(f"scheduler: {exc}")

        # 5. Invalidate any pending confirmation tokens
        try:
            from security.confirmation import get_confirmation_manager
            get_confirmation_manager().invalidate_all(reason="Application shutdown")
        except Exception:
            pass

        # 6. Teardown widgets safely
        try:
            super().destroy()
        except Exception:
            pass

        if incomplete_reasons:
            shutdown_status = "SHUTDOWN_INCOMPLETE"
            import logging
            logging.getLogger("oliver.shutdown").warning(
                "Shutdown completed with incomplete tasks: %s", "; ".join(incomplete_reasons)
            )
        self._shutdown_status = shutdown_status

    def run(self) -> None:
        self.mainloop()


# Backward-compatibility aliases
OliverApp = AshishApp
AyraApp = AshishApp
