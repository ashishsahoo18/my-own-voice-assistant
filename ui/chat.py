"""Premium chat panel for AYRA AI."""

from __future__ import annotations

import threading
import time
import tkinter as tk
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from ai.assistant import AyraAssistant
from database.chat_db import ChatStore
from voice.voice_manager import VoiceManager


class ChatBubble:
    """Render a single modern chat bubble with copy support."""

    def __init__(
        self,
        parent: ctk.CTkFrame,
        role: str,
        text: str,
        timestamp: Optional[str] = None,
    ) -> None:
        self.role = role
        self.text = text
        self.timestamp = timestamp or datetime.now().strftime("%I:%M %p")

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="x", pady=8)

        is_user = role == "user"
        anchor = "e" if is_user else "w"
        bubble_color = "#1769ff" if is_user else "#111a2b"
        border_color = "#42b7ff" if is_user else "#23344f"

        self.container = ctk.CTkFrame(
            self.frame,
            fg_color=bubble_color,
            corner_radius=18,
            border_width=1,
            border_color=border_color,
        )
        self.container.pack(anchor=anchor, padx=(54, 8) if is_user else (8, 54))

        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 0))

        sender = "You" if is_user else "AYRA"
        ctk.CTkLabel(
            header,
            text=sender,
            font=("Segoe UI", 11, "bold"),
            text_color="#dceeff",
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=self.timestamp,
            font=("Segoe UI", 10),
            text_color="#93a4bf",
        ).pack(side="right", padx=(10, 0))

        self.textbox = ctk.CTkTextbox(
            self.container,
            width=360,
            height=self._estimate_height(text),
            corner_radius=0,
            border_width=0,
            fg_color="transparent",
            text_color="#ffffff",
            font=("Cascadia Code" if "```" in text else "Segoe UI", 12),
            wrap="word",
            activate_scrollbars=False,
        )
        self.textbox.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        self.textbox.insert("1.0", self._format_text(text))
        self.textbox.configure(state="disabled")

        actions = ctk.CTkFrame(self.container, fg_color="transparent")
        actions.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkButton(
            actions,
            text="Copy",
            width=58,
            height=24,
            corner_radius=8,
            fg_color="#0b1220" if is_user else "#17243a",
            hover_color="#263c61",
            command=self.copy_text,
        ).pack(side="right")

    def _estimate_height(self, text: str) -> int:
        """Estimate textbox height from content length."""
        line_count = max(1, len(text) // 48 + text.count("\n") + 1)
        return min(max(line_count * 22, 42), 220)

    def _format_text(self, text: str) -> str:
        """Keep markdown readable inside tkinter."""
        return text.replace("```python", "Python code:\n").replace("```", "")

    def update_text(self, text: str) -> None:
        """Update bubble text during streaming."""
        self.text = text
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", tk.END)
        self.textbox.insert("1.0", self._format_text(text))
        self.textbox.configure(height=self._estimate_height(text), state="disabled")

    def copy_text(self) -> None:
        """Copy bubble content to the clipboard."""
        self.frame.clipboard_clear()
        self.frame.clipboard_append(self.text)


class ChatPanel(ctk.CTkFrame):
    """Right-side conversation panel for AYRA AI."""

    def __init__(
        self,
        master: tk.Misc,
        assistant: AyraAssistant,
        store: ChatStore,
        voice_manager: Optional[VoiceManager] = None,
    ) -> None:
        super().__init__(
            master,
            fg_color="#0b101c",
            corner_radius=22,
            border_width=1,
            border_color="#1d2a40",
        )

        self.assistant = assistant
        self.store = store
        self.voice_manager = voice_manager or VoiceManager()
        self.session_id = self.store.get_or_create_session()

        self._typing_active = False
        self._typing_job_id: Optional[str] = None
        self._thinking_timer_id: Optional[str] = None
        self._spinner_index = 0
        self._request_in_flight = False
        self._cooldown_until = 0.0
        self._rate_limit_seconds = 1.2

        self.status_var = ctk.StringVar(value="Ready")
        self.transcript_var = ctk.StringVar(value="Voice transcript will appear here.")

        self._build_ui()
        self._load_history()
        self._start_wake_word_listener()

    def _build_ui(self) -> None:
        """Build chat header, message list, transcript, and bottom bar."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Conversation",
            font=("Segoe UI", 22, "bold"),
            text_color="#f8fbff",
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            textvariable=self.status_var,
            font=("Segoe UI", 12, "bold"),
            text_color="#38f7a6",
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            header,
            text="Markdown-ready chat, voice transcript, history, and AI responses",
            font=("Segoe UI", 12),
            text_color="#8ea4c8",
            anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.chat_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#080d18",
            corner_radius=18,
            border_width=1,
            border_color="#172033",
        )
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.chat_frame.grid_columnconfigure(0, weight=1)

        transcript = ctk.CTkFrame(
            self,
            fg_color="#101827",
            corner_radius=14,
            border_width=1,
            border_color="#1d2a40",
        )
        transcript.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        transcript.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            transcript,
            text="VOICE TRANSCRIPT",
            font=("Segoe UI", 10, "bold"),
            text_color="#5bbcff",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))

        ctk.CTkLabel(
            transcript,
            textvariable=self.transcript_var,
            font=("Segoe UI", 12),
            text_color="#cbd7ee",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 8))

        self._build_input_bar()
        self._add_welcome_message()

    def _build_input_bar(self) -> None:
        """Build bottom command controls."""
        input_bar = ctk.CTkFrame(self, fg_color="transparent")
        input_bar.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        input_bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_bar,
            placeholder_text="Ask AYRA anything...",
            height=48,
            corner_radius=16,
            fg_color="#101827",
            border_color="#2a3b58",
            text_color="#f8fbff",
            placeholder_text_color="#7d8da8",
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", self._on_entry_return)

        buttons = [
            ("Mic", self.start_voice_input, "#1477ff"),
            ("Send", self.send_message, "#1769ff"),
            ("Stop", self.stop_speaking, "#253149"),
            ("Clear", self.clear_chat, "#253149"),
            ("Settings", self._request_settings, "#253149"),
        ]

        for index, (text, command, color) in enumerate(buttons, start=1):
            ctk.CTkButton(
                input_bar,
                text=text,
                width=76,
                height=48,
                corner_radius=16,
                fg_color=color,
                hover_color="#2491ff" if color.startswith("#1") else "#34435f",
                command=command,
            ).grid(row=0, column=index, padx=(0, 8 if index < len(buttons) else 0))

    def _add_welcome_message(self) -> None:
        """Add the initial premium welcome card."""
        self.welcome_card = ctk.CTkFrame(
            self.chat_frame,
            fg_color="#101827",
            corner_radius=18,
            border_width=1,
            border_color="#1d2a40",
        )
        self.welcome_card.pack(fill="x", padx=8, pady=10)

        ctk.CTkLabel(
            self.welcome_card,
            text="Welcome to AYRA AI",
            font=("Segoe UI", 20, "bold"),
            text_color="#f8fbff",
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            self.welcome_card,
            text="Ask questions, control apps, search the web, debug Python, or talk naturally with voice.",
            font=("Segoe UI", 13),
            text_color="#aab8d0",
            justify="left",
            wraplength=460,
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _on_entry_return(self, event: tk.Event) -> str:
        self.send_message()
        return "break"

    def send_message(self) -> None:
        """Send typed text to the assistant without freezing the UI."""
        if self._typing_active or self._request_in_flight:
            return

        if time.monotonic() < self._cooldown_until:
            self._set_status("Please wait")
            return

        message = self.entry.get().strip()
        if not message:
            return

        self._clear_welcome_if_present()
        self._add_message("user", message)
        self.store.save_message(self.session_id, "user", message)

        self.entry.delete(0, tk.END)
        self._cooldown_until = time.monotonic() + self._rate_limit_seconds
        self._request_in_flight = True
        self._set_busy_state(True)
        self._show_typing_indicator()
        self._set_status("Thinking")

        self._thinking_timer_id = self.after(2000, self._show_delayed_thinking_indicator)

        thread = threading.Thread(
            target=self._handle_ai_reply,
            args=(message,),
            daemon=True,
        )
        thread.start()

    def _handle_ai_reply(self, message: str) -> None:
        """Run assistant request in a background thread."""
        try:
            reply = self.assistant.handle(message)
        except Exception:
            reply = self._friendly_error_message()

        self.after(0, self._start_streaming_reply, reply)

    def _start_streaming_reply(self, reply: str) -> None:
        """Start streaming the assistant reply into the UI."""
        if self._thinking_timer_id is not None:
            self.after_cancel(self._thinking_timer_id)
            self._thinking_timer_id = None

        self._hide_typing_indicator()
        self._request_in_flight = False
        self._set_busy_state(False)
        self._stream_reply(reply)

    def _stream_reply(self, reply: str) -> None:
        """Render a word-by-word response animation."""
        if not reply:
            reply = "I do not have a response for that yet."

        self._set_status("Speaking")

        if self.voice_manager.settings.get("auto_speaking", True):
            thread = threading.Thread(
                target=self.voice_manager.speak,
                args=(reply,),
                daemon=True,
            )
            thread.start()

        bubble = ChatBubble(self.chat_frame, "assistant", "")
        self._scroll_to_bottom()

        words = reply.split()
        self._stream_words(bubble, words, 0, reply)

    def _stream_words(
        self,
        bubble: ChatBubble,
        words: list[str],
        index: int,
        full_reply: str,
    ) -> None:
        """Update assistant bubble one word at a time."""
        if index >= len(words):
            bubble.update_text(full_reply)
            self.store.save_message(self.session_id, "assistant", full_reply)
            self._set_status("Ready")
            self._scroll_to_bottom()
            return

        bubble.update_text(" ".join(words[: index + 1]))
        self._scroll_to_bottom()
        self.after(28, self._stream_words, bubble, words, index + 1, full_reply)

    def _add_message(self, role: str, text: str) -> None:
        self._clear_welcome_if_present()
        ChatBubble(self.chat_frame, role, text)
        self._scroll_to_bottom()

    def add_assistant_message(self, text: str) -> None:
        """Public helper used by the main app shell."""
        self._add_message("assistant", text)

    def _show_typing_indicator(self) -> None:
        self._typing_active = True
        self._typing_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self._typing_frame.pack(fill="x", pady=8)

        self._typing_label = ctk.CTkLabel(
            self._typing_frame,
            text="AYRA is thinking...",
            justify="left",
            corner_radius=16,
            fg_color="#111a2b",
            text_color="#dceeff",
            padx=14,
            pady=10,
        )
        self._typing_label.pack(anchor="w", padx=8)

        self._scroll_to_bottom()
        self._update_typing_indicator()

    def _update_typing_indicator(self) -> None:
        if not self._typing_active:
            return

        dots = "." * ((self._spinner_index % 3) + 1)
        self._typing_label.configure(text=f"AYRA is thinking{dots}")
        self._spinner_index += 1
        self._typing_job_id = self.after(180, self._update_typing_indicator)

    def _show_delayed_thinking_indicator(self) -> None:
        if self._typing_active:
            self._set_status("Still thinking")

    def _hide_typing_indicator(self) -> None:
        self._typing_active = False

        if self._typing_job_id is not None:
            self.after_cancel(self._typing_job_id)
            self._typing_job_id = None

        if getattr(self, "_typing_frame", None) is not None:
            self._typing_frame.destroy()
            self._typing_frame = None

    def _set_busy_state(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.entry.configure(state=state)
        self.send_btn_state = state

    def _set_status(self, status: str) -> None:
        self.status_var.set(status)

    def _scroll_to_bottom(self) -> None:
        self.update_idletasks()
        if hasattr(self.chat_frame, "_parent_canvas"):
            self.chat_frame._parent_canvas.yview_moveto(1.0)

    def _clear_welcome_if_present(self) -> None:
        if getattr(self, "welcome_card", None) is not None:
            self.welcome_card.destroy()
            self.welcome_card = None

    def _load_history(self) -> None:
        sessions = self.store.load_all_sessions()

        if not sessions:
            self._show_session_header()
            return

        for session in sessions:
            self._show_session_header(session.get("started_at"))
            for message in session.get("messages", []):
                self._add_message(message["role"], message["content"])

    def _show_session_header(self, started_at: Optional[str] = None) -> None:
        if started_at is None:
            started_at = datetime.now().strftime("%A, %B %d, %Y %I:%M %p")

        self._add_system_notice(started_at)

    def _add_system_notice(self, text: str) -> None:
        label = ctk.CTkLabel(
            self.chat_frame,
            text=text,
            justify="center",
            wraplength=460,
            font=("Segoe UI", 11),
            text_color="#7d8da8",
        )
        label.pack(pady=(8, 4))

    def start_voice_input(self) -> None:
        if self._typing_active:
            return

        self._set_status("Listening")
        thread = threading.Thread(target=self._handle_voice_input, daemon=True)
        thread.start()

    def _handle_voice_input(self) -> None:
        """Listen once, show transcript, and send it like a real conversation."""
        try:
            text = self.voice_manager.listen_once(status_callback=self._update_voice_status)
        except Exception:
            self.after(0, self._set_status, "Ready")
            self.after(0, self._show_voice_feedback, "Sorry, I did not catch that.")
            return

        if not text:
            self.after(0, self._set_status, "Ready")
            self.after(0, self._show_voice_feedback, "Sorry, I did not catch that.")
            return

        self.after(0, self.transcript_var.set, text)
        self.after(0, self.entry.delete, 0, tk.END)
        self.after(0, self.entry.insert, 0, text)
        self.after(0, self.entry.icursor, len(text))

        self.after(250, self.send_message)

    def _update_voice_status(self, status: str) -> None:
        clean_status = status.encode("ascii", "ignore").decode().strip() or "Listening"
        self.after(0, self._set_status, clean_status)

    def _show_voice_feedback(self, message: str) -> None:
        self.transcript_var.set(message)
        self._add_message("assistant", message)
        threading.Thread(target=self.voice_manager.speak, args=(message,), daemon=True).start()

    def stop_speaking(self) -> None:
        self.voice_manager.stop_speaking()
        self._set_status("Ready")

    def clear_chat(self) -> None:
        """Clear visible chat messages."""
        for child in self.chat_frame.winfo_children():
            child.destroy()
        self._add_welcome_message()

    def _request_settings(self) -> None:
        """Ask the parent app to open settings."""
        self.event_generate("<<OpenVoiceSettings>>", when="tail")

    def _start_wake_word_listener(self) -> None:
        self.voice_manager.start_wake_word_listener(self._handle_wake_word)

    def _handle_wake_word(self) -> None:
        """Start listening when the wake word is detected."""
        self.after(0, self._set_status, "Listening")
        self.after(0, self.transcript_var.set, "Wake word detected: Hey Ayra")
        self.after(300, self.start_voice_input)

    def _friendly_error_message(self) -> str:
        return "I am sorry, I could not process that request right now."