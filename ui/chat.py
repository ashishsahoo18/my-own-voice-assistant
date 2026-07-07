import threading
import tkinter as tk
from datetime import datetime
from typing import Optional

import customtkinter as ctk

from ai.assistant import AyraAssistant
from database.chat_db import ChatStore
from voice.voice_manager import VoiceManager


class ChatBubble:
    """Render a single chat bubble in the UI."""

    def __init__(self, parent: ctk.CTkFrame, role: str, text: str) -> None:
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="x", pady=6)

        if role == "user":
            self.label = ctk.CTkLabel(
                self.frame,
                text=text,
                justify="left",
                wraplength=650,
                corner_radius=16,
                fg_color=("#1f6feb", "#2b6cff"),
                text_color="white",
                padx=14,
                pady=10,
            )
            self.label.pack(anchor="e")
        else:
            self.label = ctk.CTkLabel(
                self.frame,
                text=text,
                justify="left",
                wraplength=650,
                corner_radius=16,
                fg_color=("#2a2d31", "#33373d"),
                text_color=("#f2f4f8", "#f2f4f8"),
                padx=14,
                pady=10,
            )
            self.label.pack(anchor="w")


class ChatPanel(ctk.CTkFrame):
    """Chat interface panel for Ayra."""

    def __init__(
        self,
        master: tk.Misc,
        assistant: AyraAssistant,
        store: ChatStore,
        voice_manager: Optional[VoiceManager] = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.assistant = assistant
        self.store = store
        self.session_id = self.store.get_or_create_session()
        self._typing_active = False
        self._typing_job_id: Optional[str] = None
        self._spinner_index = 0
        self.voice_manager = voice_manager or VoiceManager()
        self._voice_status = "🟢 Idle"
        self._build_ui()
        self._load_history()
        self._start_wake_word_listener()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_title = ctk.CTkLabel(
            self,
            text="Good day, how can I help?",
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        )
        self.header_title.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 4))

        self.header_subtitle = ctk.CTkLabel(
            self,
            text="AI chat • voice • automation",
            font=("Segoe UI", 12),
            text_color=("#6b7280", "#9ca3af"),
            anchor="w",
        )
        self.header_subtitle.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 10))

        self.status_label = ctk.CTkLabel(
            self,
            text="🟢 Idle",
            font=("Segoe UI", 12, "bold"),
            text_color=("#16a34a", "#4ade80"),
            anchor="w",
        )
        self.status_label.grid(row=2, column=0, sticky="w", padx=20, pady=(0, 10))

        self.chat_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.chat_frame.grid(row=3, column=0, sticky="nsew", padx=20)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        input_bar = ctk.CTkFrame(self, fg_color="transparent")
        input_bar.grid(row=4, column=0, sticky="sew", padx=20, pady=20)
        input_bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_bar,
            placeholder_text="Ask Ayra anything...",
            height=46,
            corner_radius=18,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry.bind("<Return>", self._on_entry_return)
        self.entry.bind("<Shift-Return>", self._on_shift_enter)

        self.voice_btn = ctk.CTkButton(
            input_bar,
            text="🎤",
            width=50,
            height=46,
            corner_radius=18,
            command=self.start_voice_input,
        )
        self.voice_btn.grid(row=0, column=1, padx=(0, 10))

        self.send_btn = ctk.CTkButton(
            input_bar,
            text="Send",
            width=90,
            height=46,
            corner_radius=18,
            command=self.send_message,
        )
        self.send_btn.grid(row=0, column=2)

        self.stop_speech_btn = ctk.CTkButton(
            input_bar,
            text="Stop",
            width=70,
            height=46,
            corner_radius=18,
            command=self.stop_speaking,
        )
        self.stop_speech_btn.grid(row=0, column=3)

        self._add_welcome_message()

    def _add_welcome_message(self) -> None:
        welcome = ctk.CTkFrame(self.chat_frame, fg_color=("#ffffff", "#121723"))
        welcome.pack(fill="x", pady=10, ipady=12)

        ctk.CTkLabel(
            welcome,
            text="👋 Welcome to Ayra AI",
            font=("Segoe UI", 20, "bold"),
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            welcome,
            text="Ask anything, control apps, search the web, or talk naturally with voice.",
            font=("Segoe UI", 13),
            justify="left",
            wraplength=680,
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        ctk.CTkButton(
            welcome,
            text="Start a conversation",
            command=lambda: self.entry.focus_set(),
        ).pack(anchor="w", padx=16, pady=(0, 12))

    def _on_entry_return(self, event: tk.Event) -> str:
        if self._typing_active:
            return "break"
        self.send_message()
        return "break"

    def _on_shift_enter(self, event: tk.Event) -> str:
        current = self.entry.get()
        self.entry.insert(tk.INSERT, "\n")
        return "break"

    def send_message(self) -> None:
        if self._typing_active:
            return

        message = self.entry.get().strip()
        if not message:
            return

        self._clear_welcome_if_present()
        self._add_message("user", message)
        self.store.save_message(self.session_id, "user", message)
        self.entry.delete(0, tk.END)
        self._set_busy_state(True)
        self._show_typing_indicator()
        self._set_voice_status("Thinking...")
        self.update_idletasks()
        self._thinking_timer_id = self.after(2000, self._show_delayed_thinking_indicator)

        thread = threading.Thread(target=self._handle_ai_reply, args=(message,), daemon=True)
        thread.start()

    def _handle_ai_reply(self, message: str) -> None:
        try:
            reply = self.assistant.handle(message)
        except Exception:
            reply = self._friendly_error_message()

        self.after(0, self._start_streaming_reply, reply)

    def _start_streaming_reply(self, reply: str) -> None:
        self.after_cancel(getattr(self, "_thinking_timer_id", None))
        self._hide_typing_indicator()
        self._set_busy_state(False)
        self._set_voice_status("🟢 Idle")
        self._stream_reply(reply)

    def _stream_reply(self, reply: str) -> None:
        if not reply:
            reply = "I don't have a response for that yet."

        self._set_voice_status("🔊 Speaking")
        if self.voice_manager.settings.get("auto_speaking", True):
            thread = threading.Thread(target=self.voice_manager.speak, args=(reply,), daemon=True)
            thread.start()

        bubble = ChatBubble(self.chat_frame, "assistant", "")
        bubble.label.configure(text="")
        self._scroll_to_bottom()

        words = reply.split(" ")
        if not words:
            words = [reply]

        self._stream_words(bubble.label, words, 0, reply)

    def _stream_words(self, label: ctk.CTkLabel, words: list[str], index: int, full_reply: str) -> None:
        if index >= len(words):
            self.store.save_message(self.session_id, "assistant", full_reply)
            self._set_voice_status("🟢 Idle")
            self._scroll_to_bottom()
            return

        displayed = " ".join(words[: index + 1])
        label.configure(text=displayed)
        self._scroll_to_bottom()
        self.after(35, self._stream_words, label, words, index + 1, full_reply)

    def _add_message(self, role: str, text: str) -> None:
        self._clear_welcome_if_present()
        bubble = ChatBubble(self.chat_frame, role, text)
        self._scroll_to_bottom()

    def _show_typing_indicator(self) -> None:
        self._typing_active = True
        self._typing_frame = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        self._typing_frame.pack(fill="x", pady=6)
        self._typing_label = ctk.CTkLabel(
            self._typing_frame,
            text="⠋ Ayra is typing...",
            justify="left",
            wraplength=650,
            corner_radius=16,
            fg_color=("#2a2d31", "#33373d"),
            text_color=("#f2f4f8", "#f2f4f8"),
            padx=14,
            pady=10,
        )
        self._typing_label.pack(anchor="w")
        self._scroll_to_bottom()
        self._update_typing_indicator()

    def _update_typing_indicator(self) -> None:
        if not self._typing_active:
            return

        spinner_chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        spinner = spinner_chars[self._spinner_index % len(spinner_chars)]
        self._typing_label.configure(text=f"{spinner} Thinking...")
        self._spinner_index = (self._spinner_index + 1) % len(spinner_chars)
        self._typing_job_id = self.after(120, self._update_typing_indicator)

    def _show_delayed_thinking_indicator(self) -> None:
        if not getattr(self, "_typing_active", False):
            return
        if getattr(self, "_typing_label", None) is not None:
            self._typing_label.configure(text="Thinking...")
        self._set_voice_status("Thinking...")

    def _hide_typing_indicator(self) -> None:
        self._typing_active = False
        if self._typing_job_id is not None:
            self.after_cancel(self._typing_job_id)
            self._typing_job_id = None
        if getattr(self, "_typing_frame", None) is not None:
            self._typing_frame.destroy()

    def _set_busy_state(self, busy: bool) -> None:
        self.send_btn.configure(state="disabled" if busy else "normal")
        self.entry.configure(state="disabled" if busy else "normal")
        self.voice_btn.configure(state="disabled" if busy else "normal")

    def _set_voice_status(self, status: str) -> None:
        self._voice_status = status
        self.status_label.configure(text=status)

    def _scroll_to_bottom(self) -> None:
        self.update_idletasks()
        if hasattr(self.chat_frame, "_parent_canvas"):
            self.chat_frame._parent_canvas.yview_moveto(1.0)

    def _clear_welcome_if_present(self) -> None:
        for child in list(self.chat_frame.winfo_children()):
            if isinstance(child, ctk.CTkFrame):
                for grandchild in child.winfo_children():
                    if hasattr(grandchild, "cget") and grandchild.cget("text") == "👋 Welcome to Ayra AI":
                        child.destroy()
                        return

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
        self._add_system_notice(f"{started_at}")

    def _add_system_notice(self, text: str) -> None:
        label = ctk.CTkLabel(
            self.chat_frame,
            text=text,
            justify="center",
            wraplength=680,
            font=("Segoe UI", 11),
            text_color=("#6b7280", "#9ca3af"),
        )
        label.pack(pady=(8, 4))

    def start_voice_input(self) -> None:
        if self._typing_active:
            return
        self._set_voice_status("🎤 Listening")
        thread = threading.Thread(target=self._handle_voice_input, daemon=True)
        thread.start()

    def _handle_voice_input(self) -> None:
        try:
            text = self.voice_manager.listen_once(status_callback=self._update_voice_status)
        except Exception as exc:
            self.after(0, self._set_voice_status, "🟢 Idle")
            self.after(0, self._show_voice_feedback, "Sorry, I didn't catch that.")
            return

        self.after(0, self._set_voice_status, "🟢 Idle")
        if not text:
            self.after(0, self._show_voice_feedback, "Sorry, I didn't catch that.")
            return

        self.after(0, self._show_voice_feedback, "I understood.")
        self.after(0, self.entry.insert, 0, text)
        self.after(0, self.entry.icursor, len(text))
        if self.voice_manager.settings.get("auto_send_voice", False):
            self.after(0, self.send_message)

    def _update_voice_status(self, status: str) -> None:
        self.after(0, self._set_voice_status, status)

    def _show_voice_feedback(self, message: str) -> None:
        self.voice_manager.speak(message)
        self._add_message("assistant", message)

    def stop_speaking(self) -> None:
        self.voice_manager.stop_speaking()

    def _start_wake_word_listener(self) -> None:
        self.voice_manager.start_wake_word_listener(self._handle_wake_word)

    def _handle_wake_word(self) -> None:
        self.after(0, self._set_voice_status, "🎤 Listening")
        self.after(0, self._show_voice_feedback, "Hello Ashu, I'm listening.")

    def _friendly_error_message(self) -> str:
        return "I’m sorry, I couldn’t process that request right now."
