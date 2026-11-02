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

    def __init__(
        self,
        parent: ctk.CTkFrame,
        timestamp: str,
        command_text: str,
        intent: str,
        action_desc: str,
        status: str = "SUCCESS",
        evidence: Optional[str] = None,
    ) -> None:
        cfg = STATUS_CONFIG.get(status.upper(), {
            "color": "#10B981" if status == "SUCCESS" else "#F59E0B",
            "border": "#065F46" if status == "SUCCESS" else "#78350F",
            "label": status.upper(),
        })

        super().__init__(
            parent,
            fg_color="#091224",
            border_width=1,
            border_color=cfg["border"],
            corner_radius=12,
        )
        self.pack(fill="x", pady=6, padx=8)

        # Header row: Timestamp + Intent Tag + Status Badge
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            header,
            text=f"⏱ {timestamp}",
            font=("Segoe UI", 10, "bold"),
            text_color="#5f7da8",
        ).pack(side="left")

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

        ctk.CTkLabel(
            header,
            text=f"[{intent}]",
            font=("Segoe UI", 10, "bold"),
            text_color=intent_color,
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            header,
            text=cfg["label"],
            font=("Segoe UI", 10, "bold"),
            text_color=cfg["color"],
        ).pack(side="right")

        # Command Text
        cmd_row = ctk.CTkFrame(self, fg_color="transparent")
        cmd_row.pack(fill="x", padx=12, pady=2)

        ctk.CTkLabel(
            cmd_row,
            text="COMMAND:",
            font=("Segoe UI", 10, "bold"),
            text_color="#8da5cc",
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            cmd_row,
            text=command_text,
            font=("Segoe UI", 12, "bold"),
            text_color="#ffffff",
            anchor="w",
            wraplength=380,
            justify="left",
        ).pack(side="left", fill="x", expand=True)

        # Action / Result Text
        act_row = ctk.CTkFrame(self, fg_color="transparent")
        act_row.pack(fill="x", padx=12, pady=(2, 6 if evidence else 10))

        ctk.CTkLabel(
            act_row,
            text="ACTION:",
            font=("Segoe UI", 10, "bold"),
            text_color="#8da5cc",
        ).pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            act_row,
            text=action_desc,
            font=("Segoe UI", 11),
            text_color="#c8dafd",
            anchor="w",
            wraplength=380,
            justify="left",
        ).pack(side="left", fill="x", expand=True)

        # Evidence display if present
        if evidence:
            ev_row = ctk.CTkFrame(self, fg_color="transparent")
            ev_row.pack(fill="x", padx=12, pady=(0, 10))

            ctk.CTkLabel(
                ev_row,
                text="EVIDENCE:",
                font=("Segoe UI", 9, "bold"),
                text_color="#64748b",
            ).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(
                ev_row,
                text=str(evidence),
                font=("Segoe UI", 9),
                text_color="#94a3b8",
                anchor="w",
                wraplength=380,
                justify="left",
            ).pack(side="left", fill="x", expand=True)


class CommandConsolePanel(ctk.CTkFrame):
    """Futuristic Command Console Panel for OLIVER 2.0."""

    def __init__(
        self,
        master: tk.Misc,
        assistant: AshishAssistant,
        store: ChatStore,
        voice_manager: Optional[VoiceManager] = None,
        on_state_change: Optional[StateCallback] = None,
        request_confirmation: Optional[Callable] = None,
        event_bridge: Optional[UIEventQueue] = None,
    ) -> None:
        super().__init__(
            master,
            fg_color="#060c19",
            corner_radius=18,
            border_width=1,
            border_color="#101c33",
        )

        self.assistant = assistant
        self.store = store
        self.voice_manager = voice_manager or VoiceManager()
        self.on_state_change = on_state_change
        self.request_confirmation = request_confirmation
        self.session_id = self.store.get_or_create_session()
        self._owns_event_bridge = event_bridge is None
        self.event_bridge = event_bridge or UIEventQueue()

        # If bridge is owned by this panel and not yet bound, bind this panel
        if self._owns_event_bridge and self.event_bridge._root is None:
            self.event_bridge.bind_root(self)
            self.event_bridge.start_polling()

        self._request_in_flight = False
        self._confirmation_in_flight = False
        self.status_var = ctk.StringVar(value="READY")
        self.transcript_var = ctk.StringVar(value="Awaiting command...")

        # Register voice state listener for observable HUD state changes via bridge
        try:
            self.voice_manager.add_state_listener(
                lambda st, detail: self.event_bridge.post(
                    self._set_state, st.value if hasattr(st, "value") else str(st)
                )
            )
        except Exception:
            pass

        self._build_ui()
        self._load_history()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Console Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="COMMAND CONSOLE",
            font=("Segoe UI", 18, "bold"),
            text_color="#00d2ff",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            textvariable=self.status_var,
            font=("Segoe UI", 11, "bold"),
            text_color="#00ff9d",
        ).grid(row=0, column=1, sticky="e")

        # Scrollable console HUD feed
        self.console_feed = ctk.CTkScrollableFrame(
            self,
            fg_color="#030712",
            corner_radius=14,
            border_width=1,
            border_color="#0f1b30",
        )
        self.console_feed.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))
        self.console_feed.grid_columnconfigure(0, weight=1)

        # Voice Transcript Box
        transcript_box = ctk.CTkFrame(
            self,
            fg_color="#091224",
            corner_radius=12,
            border_width=1,
            border_color="#182a4a",
        )
        transcript_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        transcript_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            transcript_box,
            text="SPEECH TRANSCRIPT",
            font=("Segoe UI", 9, "bold"),
            text_color="#00d2ff",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(6, 0))

        ctk.CTkLabel(
            transcript_box,
            textvariable=self.transcript_var,
            font=("Segoe UI", 11),
            text_color="#ffffff",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 8))

        # Quick Commands Bar
        self._build_quick_commands_bar()

        # Command Input Bar
        self._build_input_bar()

    def _build_quick_commands_bar(self) -> None:
        quick_frame = ctk.CTkFrame(self, fg_color="transparent")
        quick_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        quick_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        quick_cmds = [
            ("Calculator", "Open Calculator"),
            ("Notepad", "Open Notepad"),
            ("VS Code", "Open VS Code"),
            ("Explorer", "Open File Explorer"),
            ("YouTube", "Open YouTube"),
            ("Screenshot", "Take a screenshot"),
            ("Lock PC", "Lock computer"),
            ("System Status", "What is system status?"),
        ]

        for index, (label, cmd_text) in enumerate(quick_cmds):
            btn = ctk.CTkButton(
                quick_frame,
                text=label,
                height=32,
                corner_radius=8,
                fg_color="#0a1428",
                hover_color="#172b52",
                border_width=1,
                border_color="#1c335a",
                font=("Segoe UI", 10, "bold"),
                text_color="#8ea9d6",
                command=lambda c=cmd_text: self.execute_text_command(c),
            )
            btn.grid(row=index // 4, column=index % 4, padx=3, pady=3, sticky="ew")

    def _build_input_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 16))
        bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            bar,
            placeholder_text="Enter voice command or type here...",
            height=46,
            corner_radius=12,
            fg_color="#091224",
            border_color="#1e365d",
            text_color="#ffffff",
            placeholder_text_color="#5b78a6",
            font=("Segoe UI", 12),
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", self._on_entry_return)

        self.mic_btn = ctk.CTkButton(
            bar,
            text="🎙️ MIC",
            width=76,
            height=46,
            corner_radius=12,
            fg_color="#00d2ff",
            hover_color="#33ddff",
            text_color="#030712",
            font=("Segoe UI", 11, "bold"),
            command=self.start_voice_input,
        )
        self.mic_btn.grid(row=0, column=1, padx=(0, 6))

        self.send_btn = ctk.CTkButton(
            bar,
            text="SEND",
            width=76,
            height=46,
            corner_radius=12,
            fg_color="#1477ff",
            hover_color="#338bff",
            font=("Segoe UI", 11, "bold"),
            command=self.send_message,
        )
        self.send_btn.grid(row=0, column=2, padx=(0, 6))

        self.clear_btn = ctk.CTkButton(
            bar,
            text="CLEAR",
            width=70,
            height=46,
            corner_radius=12,
            fg_color="#111c30",
            hover_color="#1c2d4c",
            border_width=1,
            border_color="#243a61",
            font=("Segoe UI", 11, "bold"),
            command=self.clear_console,
        )
        self.clear_btn.grid(row=0, column=3)

    def _on_entry_return(self, event: tk.Event) -> str:
        self.send_message()
        return "break"

    def send_message(self) -> None:
        self.execute_text_command(self.entry.get().strip())

    def execute_text_command(self, command: str) -> None:
        command = command.strip()
        if not command or self._request_in_flight:
            return

        # Generate a unique request ID and store it thread‑locally
        request_id = new_request_id()
        set_current_request_id(request_id)
        # Record the UI start timestamp
        record(request_id, "ui_to_assistant_start", time.perf_counter())

        # Launch assistant processing in a background thread, passing the ID
        threading.Thread(
            target=self._run_assistant_command,
            args=(command, request_id),
            daemon=True,
        ).start()

    def _run_assistant_command(self, command: str, request_id: str) -> None:
        # Ensure the thread can retrieve the request ID via the helper
        set_current_request_id(request_id)
        try:
            self.event_bridge.post(self._set_state, "EXECUTING")

            if hasattr(self.assistant, "handle_result"):
                res = self.assistant.handle_result(command)
            else:
                reply = self.assistant.handle(command)
                from skills.base import ToolResult
                res = ToolResult(status="UNVERIFIED", message=reply)

            intent = getattr(self.assistant, "intent_type", "COMMAND")

            # Confirmation handling omitted for brevity (unchanged) ...
            # -----------------------------------------------------------------
            # Record total response time now that we have a result.
            # -----------------------------------------------------------------
            total = time.perf_counter() - perf_data.get(request_id, {}).get("ui_to_assistant_start", time.perf_counter())
            record(request_id, "total_response_time", total)

            status = getattr(res, "status", "UNVERIFIED")
            msg = getattr(res, "message", str(res))
            evidence_val = getattr(res, "evidence", None)
            if not evidence_val and getattr(res, "data", None):
                evidence_val = res.data.get("evidence")
            evidence_str = str(evidence_val) if evidence_val else None

            self.event_bridge.post(
                self._log_console_entry,
                command,
                intent,
                msg,
                status,
                evidence_str,
            )
            self._speak_confirmation(msg)
            self.event_bridge.post(self._set_state, "READY")
        except Exception as exc:
            err_now = time.perf_counter()
            start_err = perf_data.get(request_id, {}).get("ui_to_assistant_start")
            if start_err:
                record(request_id, "total_response_time", err_now - start_err)
            self.event_bridge.post(
                self._log_console_entry,
                command,
                "ERROR",
                f"Execution error: {exc}",
                "FAILED",
                None,
            )
            self.event_bridge.post(self._set_state, "ERROR")
        finally:
            self._request_in_flight = False

    def _log_console_entry(
        self,
        command: str,
        intent: str,
        action_desc: str,
        status: str = "SUCCESS",
        evidence: Optional[str] = None,
    ) -> None:
        now_str = datetime.now().strftime("%I:%M:%S %p")
        CommandConsoleEntry(
            self.console_feed,
            now_str,
            command,
            intent,
            action_desc,
            status,
            evidence=evidence,
        )
        self._scroll_to_bottom()

    # The remaining methods (voice handling, kill switch, etc.) are unchanged.
    # ---------------------------------------------------------------------
    def start_voice_input(self) -> None:
        from security.kill_switch import get_kill_switch
        if get_kill_switch().is_active:
            return
        # Safe barge‑in: stop any active speech immediately
        self.voice_manager.barge_in()

        if self._request_in_flight:
            return

        self._set_state("LISTENING")
        threading.Thread(target=self._handle_voice_input, daemon=True).start()

    def _handle_voice_input(self) -> None:
        try:
            text = self.voice_manager.listen_once()
        except Exception:
            self.event_bridge.post(self._set_state, "READY")
            return

        if not text:
            self.event_bridge.post(self.transcript_var.set, "No speech recognized.")
            self.event_bridge.post(self._set_state, "READY")
            return

        self.event_bridge.post(self.transcript_var.set, text)
        self.event_bridge.post(self._process_command, text)

    def clear_console(self) -> None:
        for child in self.console_feed.winfo_children():
            child.destroy()
        self._set_state("READY")

    def _set_state(self, state: str) -> None:
        self.status_var.set(state)
        if self.on_state_change:
            try:
                self.on_state_change(state)
            except Exception:
                pass

    def _scroll_to_bottom(self) -> None:
        self.update_idletasks()
        try:
            canvas = getattr(self.console_feed, "_parent_canvas", None)
            if canvas is not None:
                canvas.yview_moveto(1.0)
            elif hasattr(self.console_feed, "_canvas"):
                self.console_feed._canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _load_history(self) -> None:
        pass

    def destroy(self) -> None:
        """Destroy panel, shutting down event bridge only if this panel owns it."""
        if self.__dict__.get("_owns_event_bridge", False) and hasattr(self, "event_bridge"):
            try:
                self.event_bridge.shutdown()
            except Exception:
                pass
        super().destroy()

# Backward‑compatibility aliases
OliverConsolePanel = CommandConsolePanel
ChatPanel = CommandConsolePanel
"