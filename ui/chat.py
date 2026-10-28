"""Futuristic HUD Command Console Panel for OLIVER 2.0."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk

from ai.assistant import AshishAssistant
from database.chat_db import ChatStore
from ui.event_bridge import UIEventQueue
from voice.voice_manager import VoiceManager


StateCallback = Callable[[str], None]


STATUS_CONFIG = {
    "VERIFIED": {"color": "#10B981", "border": "#065F46", "label": "VERIFIED"},
    "UNVERIFIED": {"color": "#F59E0B", "border": "#78350F", "label": "UNVERIFIED"},
    "FAILED": {"color": "#EF4444", "border": "#7F1D1D", "label": "FAILED"},
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
            btn.grid(
                row=index // 4,
                column=index % 4,
                padx=3,
                pady=3,
                sticky="ew",
            )

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

        from security.kill_switch import get_kill_switch
        if get_kill_switch().is_active:
            self._log_console_entry(
                command,
                "SECURITY",
                "Command rejected: Emergency Kill Switch is engaged.",
                "DENIED",
                None,
            )
            return

        self.entry.delete(0, tk.END)
        self.transcript_var.set(command)
        self._process_command(command)

    def _process_command(self, command: str) -> None:
        self._request_in_flight = True
        self._set_state("PROCESSING")

        threading.Thread(
            target=self._run_assistant_command,
            args=(command,),
            daemon=True,
        ).start()

    def _execute_confirmed(self, payload: str, intent_override: str = "COMMAND") -> None:
        """Backward compatibility shim."""
        self._handle_confirmation_confirm(payload, intent_override, None, payload)

    def _cancel_confirmed(self, command: str, intent_override: str = "COMMAND", cancel_msg: str = "Command cancelled by user.") -> None:
        """Backward compatibility shim."""
        self._handle_confirmation_cancel(command, intent_override, None)

    def _run_assistant_command(self, command: str) -> None:
        try:
            self.event_bridge.post(self._set_state, "EXECUTING")

            if hasattr(self.assistant, "handle_result"):
                res = self.assistant.handle_result(command)
            else:
                reply = self.assistant.handle(command)
                from skills.base import ToolResult
                res = ToolResult(status="UNVERIFIED", message=reply)

            intent = getattr(self.assistant, "intent_type", "COMMAND")

            # Check if action requires explicit confirmation
            if getattr(res, "status", "") == "NEED_CONFIRM":
                token = res.data.get("token") if res.data else None
                preview = res.message
                payload = {
                    "token": token,
                    "tool_name": res.data.get("tool_name", "") if res.data else "",
                    "arguments": res.data.get("arguments", {}) if res.data else {},
                    "command": command,
                    "summary": preview,
                }
                if res.data and "payload" in res.data:
                    payload["payload"] = res.data["payload"]

                self.event_bridge.post(
                    self._log_console_entry,
                    command,
                    intent,
                    f"Awaiting confirmation: {preview}",
                    "NEED_CONFIRM",
                    None,
                )
                self.event_bridge.post(self._set_state, "SPEAKING")
                self.voice_manager.speak(f"Confirmation required. {preview}")

                self.event_bridge.post(
                    self._show_confirmation_dialog,
                    command,
                    intent,
                    preview,
                    token,
                    payload,
                )
                return

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
            print("OLIVER 2.0 EXECUTION ERROR:", repr(exc))
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

    def _show_confirmation_dialog(
        self,
        command: str,
        intent: str,
        preview: str,
        token: Optional[str],
        payload: Any,
    ) -> None:
        """Present confirmation modal dialog on Tkinter main thread."""
        if not self.request_confirmation:
            self._log_console_entry(
                command,
                intent,
                "No confirmation modal handler available. Action cancelled.",
                "CANCELLED",
                None,
            )
            self._set_state("READY")
            self._request_in_flight = False
            return

        self._confirmation_in_flight = False

        def on_confirm():
            if self._confirmation_in_flight:
                return
            self._confirmation_in_flight = True
            threading.Thread(
                target=self._handle_confirmation_confirm,
                args=(command, intent, token, payload),
                daemon=True,
            ).start()

        def on_cancel():
            if self._confirmation_in_flight:
                return
            self._confirmation_in_flight = True
            threading.Thread(
                target=self._handle_confirmation_cancel,
                args=(command, intent, token),
                daemon=True,
            ).start()

        self.request_confirmation(
            title="System Security Confirmation",
            message=preview,
            on_confirm=on_confirm,
            on_cancel=on_cancel,
            confirm_text="CONFIRM",
            accent_color="#ff3b30",
        )

    def _handle_confirmation_confirm(
        self,
        command: str,
        intent: str,
        token: Optional[str],
        payload: Any,
    ) -> None:
        try:
            self.event_bridge.post(self._set_state, "EXECUTING")
            if hasattr(self.assistant, "execute_confirmed_command_result"):
                res = self.assistant.execute_confirmed_command_result(payload, confirmation_token=token)
            else:
                raw_res = self.assistant.execute_confirmed_command(str(payload))
                from skills.base import ToolResult
                res = ToolResult(status="UNVERIFIED", message=raw_res)

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
            self.event_bridge.post(
                self._log_console_entry,
                command,
                intent,
                f"Confirmation execution failed: {exc}",
                "FAILED",
                None,
            )
            self.event_bridge.post(self._set_state, "ERROR")
        finally:
            self._confirmation_in_flight = False
            self._request_in_flight = False

    def _handle_confirmation_cancel(
        self,
        command: str,
        intent: str,
        token: Optional[str],
    ) -> None:
        try:
            if token:
                from security.confirmation import get_confirmation_manager
                get_confirmation_manager().invalidate_token(token, reason="User cancelled in UI")

            cancel_msg = "Action cancelled by user."
            self.event_bridge.post(
                self._log_console_entry,
                command,
                intent,
                cancel_msg,
                "CANCELLED",
                None,
            )
            self._speak_confirmation(cancel_msg)
            self.event_bridge.post(self._set_state, "READY")
        finally:
            self._confirmation_in_flight = False
            self._request_in_flight = False

    def _speak_confirmation(self, reply: str) -> None:
        self.voice_manager.speak(reply)

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

    def start_voice_input(self) -> None:
        from security.kill_switch import get_kill_switch
        if get_kill_switch().is_active:
            return

        # Safe barge-in: stop any active speech immediately
        self.voice_manager.barge_in()

        if self._request_in_flight:
            return

        self._set_state("LISTENING")
        threading.Thread(target=self._handle_voice_input, daemon=True).start()

    def handle_kill_switch_activated(self) -> None:
        """Disable inputs and log emergency stop activation."""
        try:
            self.entry.configure(state="disabled")
        except Exception:
            pass
        if hasattr(self, "mic_btn"):
            try:
                self.mic_btn.configure(state="disabled")
            except Exception:
                pass
        if hasattr(self, "send_btn"):
            try:
                self.send_btn.configure(state="disabled")
            except Exception:
                pass
        self._set_state("KILLED")
        self._log_console_entry(
            "EMERGENCY STOP",
            "SECURITY",
            "Emergency Kill Switch engaged. All executions and speech halted.",
            "CANCELLED",
            None,
        )

    def handle_kill_switch_deactivated(self) -> None:
        """Re-enable inputs and log emergency stop reset."""
        try:
            self.entry.configure(state="normal")
        except Exception:
            pass
        if hasattr(self, "mic_btn"):
            try:
                self.mic_btn.configure(state="normal")
            except Exception:
                pass
        if hasattr(self, "send_btn"):
            try:
                self.send_btn.configure(state="normal")
            except Exception:
                pass
        self._set_state("READY")
        self._log_console_entry(
            "RESET KILL SWITCH",
            "SECURITY",
            "Emergency Kill Switch disengaged. Normal operations restored.",
            "VERIFIED",
            None,
        )

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


# Backward-compatibility aliases
OliverConsolePanel = CommandConsolePanel
ChatPanel = CommandConsolePanel