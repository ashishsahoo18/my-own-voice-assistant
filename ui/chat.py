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
    """Single chat bubble."""

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

        is_user = role == "user"
        anchor = "e" if is_user else "w"
        bubble_color = "#1f78ff" if is_user else "#121c2f"
        border_color = "#4cc9ff" if is_user else "#263a5c"

        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", pady=8, padx=10)

        self.frame = ctk.CTkFrame(
            outer,
            fg_color=bubble_color,
            border_width=1,
            border_color=border_color,
            corner_radius=18,
        )
        self.frame.pack(anchor=anchor, padx=(90, 8) if is_user else (8, 90))

        header = ctk.CTkFrame(self.frame, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 2))

        ctk.CTkLabel(
            header,
            text="You" if is_user else "AYRA",
            font=("Segoe UI", 11, "bold"),
            text_color="#ffffff",
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=self.timestamp,
            font=("Segoe UI", 10),
            text_color="#b8c7e6",
        ).pack(side="right", padx=(16, 0))

        self.message_label = ctk.CTkLabel(
            self.frame,
            text=text,
            font=("Segoe UI", 13),
            text_color="#ffffff",
            justify="left",
            anchor="w",
            wraplength=430,
        )
        self.message_label.pack(fill="x", padx=14, pady=(8, 12))

        ctk.CTkButton(
            self.frame,
            text="Copy",
            width=64,
            height=28,
            corner_radius=10,
            fg_color="#07111f",
            hover_color="#1d3354",
            command=self.copy_text,
        ).pack(anchor="e", padx=14, pady=(0, 12))

    def update_text(self, text: str) -> None:
        self.text = text
        self.message_label.configure(text=text)

    def copy_text(self) -> None:
        self.frame.clipboard_clear()
        self.frame.clipboard_append(self.text)


class ChatPanel(ctk.CTkFrame):
    """Conversation panel for AYRA AI."""

    def __init__(
        self,
        master: tk.Misc,
        assistant: AyraAssistant,
        store: ChatStore,
        voice_manager: Optional[VoiceManager] = None,
    ) -> None:
        super().__init__(
            master,
            fg_color="#070d18",
            corner_radius=22,
            border_width=1,
            border_color="#1d2e4a",
        )

        self.assistant = assistant
        self.store = store
        self.voice_manager = voice_manager or VoiceManager()
        self.session_id = self.store.get_or_create_session()

        self._request_in_flight = False
        self._typing_active = False
        self._typing_job_id: Optional[str] = None
        self._spinner_index = 0

        self.status_var = ctk.StringVar(value="Ready")
        self.transcript_var = ctk.StringVar(value="Voice transcript will appear here.")

        self._build_ui()
        self._load_history()
        self._start_wake_word_listener()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Conversation",
            font=("Segoe UI", 22, "bold"),
            text_color="#ffffff",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            textvariable=self.status_var,
            font=("Segoe UI", 12, "bold"),
            text_color="#33f5a5",
        ).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            header,
            text="Markdown-ready chat, voice transcript, history, and AI responses",
            font=("Segoe UI", 12),
            text_color="#9bb7e8",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.chat_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#050a13",
            corner_radius=18,
            border_width=1,
            border_color="#16243b",
        )
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        self.chat_frame.grid_columnconfigure(0, weight=1)

        transcript = ctk.CTkFrame(
            self,
            fg_color="#101a2b",
            corner_radius=14,
            border_width=1,
            border_color="#203552",
        )
        transcript.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
        transcript.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            transcript,
            text="VOICE TRANSCRIPT",
            font=("Segoe UI", 10, "bold"),
            text_color="#4cc9ff",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(9, 0))

        ctk.CTkLabel(
            transcript,
            textvariable=self.transcript_var,
            font=("Segoe UI", 12),
            text_color="#ffffff",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 10))

        self._build_input_bar()

    def _build_input_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            bar,
            placeholder_text="Ask AYRA anything...",
            height=50,
            corner_radius=16,
            fg_color="#101a2b",
            border_color="#2a4771",
            text_color="#ffffff",
            placeholder_text_color="#8da2c6",
            font=("Segoe UI", 13),
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry.bind("<Return>", self._on_entry_return)

        self.mic_btn = self._button(bar, "Mic", self.start_voice_input, 1, "#1f78ff")
        self.send_btn = self._button(bar, "Send", self.send_message, 2, "#1f78ff")
        self.stop_btn = self._button(bar, "Stop", self.stop_speaking, 3, "#263652")
        self.clear_btn = self._button(bar, "Clear", self.clear_chat, 4, "#263652")
        self.settings_btn = self._button(bar, "Settings", self._request_settings, 5, "#263652")

    def _button(self, master, text: str, command, column: int, color: str) -> ctk.CTkButton:
        button = ctk.CTkButton(
            master,
            text=text,
            width=94,
            height=50,
            corner_radius=16,
            fg_color=color,
            hover_color="#3294ff" if color == "#1f78ff" else "#344766",
            command=command,
        )
        button.grid(row=0, column=column, padx=(0, 10 if column < 5 else 0))
        return button

    def _on_entry_return(self, event: tk.Event) -> str:
        self.send_message()
        return "break"

    def send_message(self) -> None:
        self.send_text_message(self.entry.get().strip())

    def send_text_message(self, message: str, force: bool = False) -> None:
        message = message.strip()
        if not message:
            return

        if self._request_in_flight and not force:
            self._set_status("Please wait")
            return

        self._add_message("user", message)

        try:
            self.store.save_message(self.session_id, "user", message)
        except Exception as exc:
            print("AYRA DATABASE ERROR:", repr(exc))

        self.entry.delete(0, tk.END)
        self._request_in_flight = True
        self._set_busy_state(True)
        self._show_typing_indicator()
        self._set_status("Thinking")

        threading.Thread(
            target=self._handle_ai_reply,
            args=(message,),
            daemon=True,
        ).start()

    def _handle_ai_reply(self, message: str) -> None:
        try:
            reply = self.assistant.handle(message)
        except Exception as exc:
            print("AYRA CHAT ERROR:", repr(exc))
            reply = f"I had trouble answering that: {exc}"

        self.after(0, self._show_assistant_reply, reply)

    def _show_assistant_reply(self, reply: str) -> None:
        self._hide_typing_indicator()
        self._request_in_flight = False
        self._set_busy_state(False)

        clean_reply = reply.strip() if reply else "I do not have a response for that yet."
        self._stream_reply(clean_reply)

    def _stream_reply(self, reply: str) -> None:
        self._set_status("Speaking")

        threading.Thread(
            target=self.voice_manager.speak,
            args=(reply,),
            daemon=True,
        ).start()

        # Create bubble directly with complete reply text so output is instantly visible in the conversation panel
        bubble = ChatBubble(self.chat_frame, "assistant", reply)
        self._scroll_to_bottom()

        try:
            self.store.save_message(self.session_id, "assistant", reply)
        except Exception as exc:
            print("AYRA DATABASE ERROR:", repr(exc))

        self._set_status("Ready")

    def _add_message(self, role: str, text: str) -> None:
        ChatBubble(self.chat_frame, role, text)
        self._scroll_to_bottom()

    def _show_typing_indicator(self) -> None:
        self._typing_active = True
        self._typing_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self._typing_frame.pack(fill="x", pady=8, padx=10)

        self._typing_label = ctk.CTkLabel(
            self._typing_frame,
            text="AYRA is thinking",
            fg_color="#121c2f",
            text_color="#ffffff",
            corner_radius=16,
            padx=16,
            pady=10,
        )
        self._typing_label.pack(anchor="w", padx=8)
        self._update_typing_indicator()

    def _update_typing_indicator(self) -> None:
        if not self._typing_active:
            return

        dots = "." * ((self._spinner_index % 3) + 1)
        self._typing_label.configure(text=f"AYRA is thinking{dots}")
        self._spinner_index += 1
        self._typing_job_id = self.after(220, self._update_typing_indicator)

    def _hide_typing_indicator(self) -> None:
        self._typing_active = False

        if self._typing_job_id is not None:
            self.after_cancel(self._typing_job_id)
            self._typing_job_id = None

        if getattr(self, "_typing_frame", None) is not None:
            self._typing_frame.destroy()
            self._typing_frame = None

    def start_voice_input(self) -> None:
        if self._request_in_flight:
            return

        self._set_status("Listening")
        threading.Thread(target=self._handle_voice_input, daemon=True).start()

    def _handle_voice_input(self) -> None:
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
        self.after(0, self.send_text_message, text, True)

    def _update_voice_status(self, status: str) -> None:
        self.after(0, self._set_status, status or "Listening")

    def _show_voice_feedback(self, message: str) -> None:
        self.transcript_var.set(message)
        self._add_message("assistant", message)
        threading.Thread(target=self.voice_manager.speak, args=(message,), daemon=True).start()

    def stop_speaking(self) -> None:
        self.voice_manager.stop_speaking()
        self._set_status("Ready")

    def clear_chat(self) -> None:
        for child in self.chat_frame.winfo_children():
            child.destroy()
        self._set_status("Ready")

    def _request_settings(self) -> None:
        self.event_generate("<<OpenVoiceSettings>>", when="tail")

    def _start_wake_word_listener(self) -> None:
        try:
            self.voice_manager.start_wake_word_listener(self._handle_wake_word)
        except Exception:
            pass

    def _handle_wake_word(self) -> None:
        self.after(0, self.start_voice_input)

    def _load_history(self) -> None:
        try:
            sessions = self.store.load_all_sessions()
        except Exception:
            return

        for session in sessions:
            for message in session.get("messages", []):
                role = str(message.get("role", "assistant"))
                content = str(message.get("content", ""))
                if content:
                    self._add_message(role, content)

    def _set_busy_state(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.entry.configure(state=state)
        self.send_btn.configure(state=state)
        self.mic_btn.configure(state=state)

    def _set_status(self, status: str) -> None:
        self.status_var.set(status)

    def _scroll_to_bottom(self) -> None:
        self.update_idletasks()
        canvas = getattr(self.chat_frame, "_parent_canvas", None)
        if canvas is not None:
            canvas.yview_moveto(1.0)