"""Futuristic HUD Command Console Panel for OLIVER 2.0.
"""

import threading
import tkinter as tk
import time
from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk

from ai.assistant import AshishAssistant
from database.chat_db import ChatStore
from ui.event_bridge import UIEventQueue
from voice.voice_manager import VoiceManager

# Performance instrumentation imports
from scratch.perf_shared import new_request_id, record, set_current_request_id, get_current_request_id

StateCallback = Callable[[str], None]

STATUS_CONFIG = {
    "VERIFIED": {"color": "#10B981", "border": "#065F46", "label": "VERIFIED"},
    "UNVERIFIED": {"color": "#F59E0B", "border": "#78350F", "label": "UNVERIFIED"},
    "FAILED": {"color": "#EF4444", "border": "#7F1D1B", "label": "FAILED"},
    "DENIED": {"color": "#991B1B", "border": "#4C0519", "label": "DENIED"},
    "CANCELLED": {"color": "#64748B", "border": "#334155", "label": "CANCELLED"},
    "TIMEOUT": {"color": "#EA580C", "border": "#7C2D12", "label": "TIMEOUT"},
    "NEED_CONFIRM": {"color": "#D97706", "border": "#78350F", "label": "NEED CONFIRM"},
    "SUCCESS": {"color": "#10B981", "border": "#065F46", "label": "VERIFIED"},
}

class CommandConsoleEntry(ctk.CTkFrame):
    """Futuristic HUD console log entry for executed assistant commands with truthful status badges."""

    def __init__(self, parent: ctk.CTkFrame, timestamp: str, command_text: str, intent: str, action_desc: str, status: str = "SUCCESS", evidence: Optional[str] = None) -> None:
        cfg = STATUS_CONFIG.get(status.upper(), {
            "color": "#10B981" if status == "SUCCESS" else "#F59E0B",
            "border": "#065F46" if status == "SUCCESS" else "#78350F",
            "label": status.upper(),
        })
        super().__init__(parent, fg_color="#091224", border_width=1, border_color=cfg["border"], corner_radius=12)
        self.pack(fill="x", pady=6, padx=8)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(header, text=f"⏱ {timestamp}", font=("Segoe UI", 10, "bold"), text_color="#5f7da8").pack(side="left")
        intent_color = "#00d2ff"
        normalized_intent = intent.upper()
        if normalized_intent in ("WINDOWS_APP", "WINDOWS_COMMAND", "WINDOWS"):
            intent_color = "#38f7a6"
        elif normalized_intent in ("YOUTUBE", "MEDIA"):
            intent_color = "#ff3b5c"
        elif normalized_intent in ("PRODUCTIVITY", "FILE_COMMAND", "FILES"):
            intent_color = "#ffb703"
        elif normalized_intent in ("COMMUNICATION", "WHATSAPP", "EMAIL"):
            intent_color = "#34d399"
        ctk.CTkLabel(header, text=f"[{intent}]", font=("Segoe UI", 10, "bold"), text_color=intent_color).pack(side="left", padx=10)
        ctk.CTkLabel(header, text=cfg["label"], font=("Segoe UI", 10, "bold"), text_color=cfg["color"]).pack(side="right")
        cmd_row = ctk.CTkFrame(self, fg_color="transparent")
        cmd_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(cmd_row, text="COMMAND:", font=("Segoe UI", 10, "bold"), text_color="#8da5cc").pack(side="left", padx=(0, 6))
        ctk.CTkLabel(cmd_row, text=command_text, font=("Segoe UI", 12, "bold"), text_color="#ffffff", anchor="w", wraplength=380, justify="left").pack(side="left", fill="x", expand=True)
        act_row = ctk.CTkFrame(self, fg_color="transparent")
        act_row.pack(fill="x", padx=12, pady=(2, 6 if evidence else 10))
        ctk.CTkLabel(act_row, text="ACTION:", font=("Segoe UI", 10, "bold"), text_color="#8da5cc").pack(side="left", padx=(0, 6))
        ctk.CTkLabel(act_row, text=action_desc, font=("Segoe UI", 11), text_color="#c8dafd", anchor="w", wraplength=380, justify="left").pack(side="left", fill="x", expand=True)
        if evidence:
            ev_row = ctk.CTkFrame(self, fg_color="transparent")
            ev_row.pack(fill="x", padx=12, pady=(0, 10))
            ctk.CTkLabel(ev_row, text="EVIDENCE:", font=("Segoe UI", 9, "bold"), text_color="#64748b").pack(side="left", padx=(0, 6))
            ctk.CTkLabel(ev_row, text=str(evidence), font=("Segoe UI", 9), text_color="#94a3b8", anchor="w", wraplength=380, justify="left").pack(side="left", fill="x", expand=True)

class CommandConsolePanel(ctk.CTkFrame):
    """Futuristic Command Console Panel for OLIVER 2.0."""
    def __init__(self, master: tk.Misc, assistant: AshishAssistant, store: ChatStore, voice_manager: Optional[VoiceManager] = None, on_state_change: Optional[StateCallback] = None, request_confirmation: Optional[Callable] = None, event_bridge: Optional[UIEventQueue] = None) -> None:
        super().__init__(master, fg_color="#060c19", corner_radius=18, border_width=1, border_color="#101c33")
        self.assistant = assistant
        self.store = store
        self.voice_manager = voice_manager or VoiceManager()
        self.on_state_change = on_state_change
        self.request_confirmation = request_confirmation
        self.session_id = self.store.get_or_create_session()
        self._owns_event_bridge = event_bridge is None
        self.event_bridge = event_bridge or UIEventQueue()
        if self._owns_event_bridge and self.event_bridge._root is None:
            self.event_bridge.bind_root(self)
            self.event_bridge.start_polling()
        self._request_in_flight = False
        self._confirmation_in_flight = False
        self.status_var = ctk.StringVar(value="READY")
        self.transcript_var = ctk.StringVar(value="Awaiting command...")
        try:
            self.voice_manager.add_state_listener(lambda st, detail: self.event_bridge.post(self._set_state, st.value if hasattr(st, "value") else str(st)))
        except Exception:
            pass
        self._build_ui()
        self._load_history()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="COMMAND CONSOLE", font=("Segoe UI", 18, "bold"), text_color="#00d2ff").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, textvariable=self.status_var, font=("Segoe UI", 11, "bold"), text_color="#00ff9d").grid(row=0, column=1, sticky="e")
        self.console_feed = ctk.CTkScrollableFrame(self, fg_color="#030712", corner_radius=14, border_width=1, border_color="#0f1b30")
        self.console_feed.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.console_feed.grid_columnconfigure(0, weight=1)
        transcript_box = ctk.CTkFrame(self, fg_color="#091224", corner_radius=12, border_width=1, border_color="#182a4a")
        transcript_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        transcript_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(transcript_box, text="SPEECH TRANSCRIPT", font=("Segoe UI", 9, "bold"), text_color="#00d2ff").grid(row=0, column=0, sticky="w", padx=12, pady=(6, 0))
        ctk.CTkLabel(transcript_box, textvariable=self.transcript_var, font=("Segoe UI", 11), text_color="#ffffff", anchor="w").grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 8))
        # Build quick‑command bar and input bar (added later)
        self._build_quick_commands_bar()
        self._build_input_bar()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="COMMAND CONSOLE", font=("Segoe UI", 18, "bold"), text_color="#00d2ff").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, textvariable=self.status_var, font=("Segoe UI", 11, "bold"), text_color="#00ff9d").grid(row=0, column=1, sticky="e")
        self.console_feed = ctk.CTkScrollableFrame(self, fg_color="#030712", corner_radius=14, border_width=1, border_color="#0f1b30")
        self.console_feed.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.console_feed.grid_columnconfigure(0, weight=1)
        transcript_box = ctk.CTkFrame(self, fg_color="#091224", corner_radius=12, border_width=1, border_color="#182a4a")
        transcript_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        transcript_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(transcript_box, text="SPEECH TRANSCRIPT", font=("Segoe UI", 9, "bold"), text_color="#00d2ff").grid(row=0, column=0, sticky="w", padx=12, pady=(6, 0))
        ctk.CTkLabel(transcript_box, textvariable=self.transcript_var, font=("Segoe UI", 11), text_color="#ffffff", anchor="w").grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 8))
        self._build_quick_commands_bar()
        self._build_input_bar()

    # (The rest of the class definitions remain unchanged.)

    # ------------------------------------------------------------------
    # QUICK‑COMMAND BAR (added to fix missing method)
    # ------------------------------------------------------------------
    def _build_quick_commands_bar(self) -> None:
        """
        Build the row of five quick‑command buttons that appear beneath the
        transcript box. Each button inserts a command prefix into the input
        entry and focuses the entry for immediate editing or submission.
        """
        bar = ctk.CTkFrame(self, fg_color="#0b172a")
        bar.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        # equally distribute columns for the five buttons
        for col in range(5):
            bar.grid_columnconfigure(col, weight=1)

        def _make_btn(label: str, insert_text: str) -> ctk.CTkButton:
            return ctk.CTkButton(
                bar,
                text=label,
                width=0,
                font=("Segoe UI", 10, "bold"),
                fg_color="#101c33",
                hover_color="#1e2b4a",
                command=lambda: (
                    self._input_entry.delete(0, tk.END),
                    self._input_entry.insert(0, insert_text),
                    self._input_entry.focus_set(),
                ),
            )

        # Create and place the five buttons
        _make_btn("Note", "!note ").grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        _make_btn("Remind", "!remind ").grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        _make_btn("Search", "!search ").grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        _make_btn("Image", "!image ").grid(row=0, column=3, padx=4, pady=4, sticky="ew")
        _make_btn("Files", "!files ").grid(row=0, column=4, padx=4, pady=4, sticky="ew")


# Backward‑compatibility aliases
OliverConsolePanel = CommandConsolePanel
ChatPanel = CommandConsolePanel
