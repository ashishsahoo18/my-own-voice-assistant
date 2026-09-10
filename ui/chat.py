"""Futuristic HUD Command Console Panel for ASHISH AI."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from typing import Callable, Optional

import customtkinter as ctk

from ai.assistant import AshishAssistant
from database.chat_db import ChatStore
from voice.voice_manager import VoiceManager


StateCallback = Callable[[str], None]


class CommandConsoleEntry(ctk.CTkFrame):
    """Futuristic HUD console log entry for executed assistant commands."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        timestamp: str,
        command_text: str,
        intent: str,
        action_desc: str,
        status: str = "SUCCESS",
    ) -> None:
        super().__init__(
            parent,
            fg_color="#091224",
            border_width=1,
            border_color="#182c4f" if status == "SUCCESS" else "#5c2424",
            corner_radius=12,
        )
        self.pack(fill="x", pady=6, padx=8)

        # Header row: Timestamp + Intent Tag + Status
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            header,
            text=f"⏱ {timestamp}",
            font=("Segoe UI", 10, "bold"),
            text_color="#5f7da8",
        ).pack(side="left")

        intent_color = "#00d2ff"
        if intent == "WINDOWS_APP" or intent == "WINDOWS_COMMAND":
            intent_color = "#38f7a6"
        elif intent == "YOUTUBE":
            intent_color = "#ff3b5c"
        elif intent == "PRODUCTIVITY" or intent == "FILE_COMMAND":
            intent_color = "#ffb703"

        ctk.CTkLabel(
            header,
            text=f"[{intent}]",
            font=("Segoe UI", 10, "bold"),
            text_color=intent_color,
        ).pack(side="left", padx=10)

        status_color = "#38f7a6" if status == "SUCCESS" else "#ff4444"
        ctk.CTkLabel(
            header,
            text=status,
            font=("Segoe UI", 10, "bold"),
            text_color=status_color,
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
        act_row.pack(fill="x", padx=12, pady=(2, 10))

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


class CommandConsolePanel(ctk.CTkFrame):
    """Futuristic Command Console Panel for ASHISH AI."""

    def __init__(
        self,
        master: tk.Misc,
        assistant: AshishAssistant,
        store: ChatStore,
        voice_manager: Optional[VoiceManager] = None,
        on_state_change: Optional[StateCallback] = None,
        request_confirmation: Optional[Callable] = None,
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

        self._request_in_flight = False
        self.status_var = ctk.StringVar(value="READY")
        self.transcript_var = ctk.StringVar(value="Awaiting command...")

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

        self.entry.delete(0, tk.END)
        self.transcript_var.set(command)
        self._process_command(command)

    def _process_command(self, command: str) -> None:
        self._request_in_flight = True
        self._set_state("PROCESSING")

        # Check dangerous command requirement
        is_dangerous, confirm_msg = self.assistant.is_dangerous_command(command)
        if is_dangerous and self.request_confirmation:
            self._set_state("SPEAKING")
            threading.Thread(
                target=self.voice_manager.speak,
                args=(confirm_msg,),
                daemon=True,
            ).start()

            self.request_confirmation(
                confirm_msg,
                on_confirm=lambda: self._execute_confirmed(command),
                on_cancel=lambda: self._cancel_confirmed(command),
            )
            return

        threading.Thread(
            target=self._run_assistant_command,
            args=(command,),
            daemon=True,
        ).start()

    def _execute_confirmed(self, command: str) -> None:
        self._set_state("EXECUTING")
        res = self.assistant.execute_confirmed_command(command)
        self._log_console_entry(command, "DANGEROUS_COMMAND", res, "SUCCESS")
        self._speak_confirmation(res)

    def _cancel_confirmed(self, command: str) -> None:
        self._set_state("READY")
        self._log_console_entry(command, "DANGEROUS_COMMAND", "Command cancelled by user.", "CANCELLED")

    def _run_assistant_command(self, command: str) -> None:
        try:
            self._set_state("EXECUTING")
            reply = self.assistant.handle(command)
            intent = getattr(self.assistant, "intent_type", "COMMAND")

            self.after(0, self._log_console_entry, command, intent, reply, "SUCCESS")
            self._speak_confirmation(reply)
        except Exception as exc:
            print("ASHISH AI EXECUTION ERROR:", repr(exc))
            self.after(0, self._log_console_entry, command, "ERROR", f"Error: {exc}", "FAILED")
            self._set_state("ERROR")
            self.after(2000, lambda: self._set_state("READY"))
        finally:
            self._request_in_flight = False

    def _speak_confirmation(self, reply: str) -> None:
        self._set_state("SPEAKING")
        self.voice_manager.speak(reply)
        self._set_state("READY")

    def _log_console_entry(
        self,
        command: str,
        intent: str,
        action_desc: str,
        status: str = "SUCCESS",
    ) -> None:
        now_str = datetime.now().strftime("%I:%M:%S %p")
        CommandConsoleEntry(
            self.console_feed,
            now_str,
            command,
            intent,
            action_desc,
            status,
        )
        self._scroll_to_bottom()

    def start_voice_input(self) -> None:
        if self._request_in_flight:
            return

        self._set_state("LISTENING")
        threading.Thread(target=self._handle_voice_input, daemon=True).start()

    def _handle_voice_input(self) -> None:
        try:
            text = self.voice_manager.listen_once()
        except Exception:
            self.after(0, self._set_state, "READY")
            return

        if not text:
            self.after(0, self.transcript_var.set, "No speech recognized.")
            self.after(0, self._set_state, "READY")
            return

        self.after(0, self.transcript_var.set, text)
        self.after(0, self._process_command, text)

    def clear_console(self) -> None:
        for child in self.console_feed.winfo_children():
            child.destroy()
        self._set_state("READY")

    def _set_state(self, state: str) -> None:
        self.status_var.set(state)
        if self.on_state_change:
            self.after(0, self.on_state_change, state)

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


# Alias for backward compatibility
ChatPanel = CommandConsolePanel