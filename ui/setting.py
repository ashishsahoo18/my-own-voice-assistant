"""Settings windows for AYRA AI."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from voice.language import VoiceLanguage
from voice.voice_manager import VoiceManager


class VoiceSettingsWindow(ctk.CTkToplevel):
    """Premium settings window for voice preferences."""

    def __init__(self, voice_manager: VoiceManager) -> None:
        super().__init__()

        self.title("AYRA AI Settings")
        self.geometry("560x640")
        self.minsize(520, 600)
        self.configure(fg_color="#070b14")

        self.voice_manager = voice_manager
        self._voice_name_to_id: dict[str, str] = {}

        self.transient()
        self.grab_set()

        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        """Build settings UI."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 14))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="AYRA Settings",
            font=("Segoe UI", 26, "bold"),
            text_color="#f8fbff",
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Voice, wake word, language, and speech behavior",
            font=("Segoe UI", 12),
            text_color="#8ea4c8",
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        body = ctk.CTkScrollableFrame(
            self,
            fg_color="#0b101c",
            corner_radius=18,
            border_width=1,
            border_color="#1d2a40",
        )
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        body.grid_columnconfigure(1, weight=1)

        self.voice_enabled = self._add_switch(body, 0, "Enable Voice")
        self.auto_speaking = self._add_switch(body, 1, "Auto Speaking")
        self.auto_send_voice = self._add_switch(body, 2, "Auto Send Voice")
        self.wake_word_enabled = self._add_switch(body, 3, "Wake Word")

        self.language_var = ctk.StringVar(value="en")
        self.language_box = self._add_option(
            body,
            4,
            "Language",
            self.language_var,
            [label for _, label in VoiceLanguage.choices()],
        )

        self.voice_var = ctk.StringVar(value="Default")
        self.voice_box = self._add_option(
            body,
            5,
            "Voice",
            self.voice_var,
            self._load_voice_names(),
        )

        self.wake_word = self._add_entry(body, 6, "Wake Word", "hey ayra")

        self.speed_var = ctk.IntVar(value=170)
        self.speed_label_var = ctk.StringVar(value="170")
        self._add_slider(
            body,
            7,
            "Speech Speed",
            self.speed_var,
            80,
            300,
            self.speed_label_var,
            self._update_speed_label,
        )

        self.volume_var = ctk.DoubleVar(value=1.0)
        self.volume_label_var = ctk.StringVar(value="100%")
        self._add_slider(
            body,
            8,
            "Volume",
            self.volume_var,
            0.0,
            1.0,
            self.volume_label_var,
            self._update_volume_label,
        )

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 24))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer,
            text="Test Voice",
            height=42,
            corner_radius=12,
            fg_color="#253149",
            hover_color="#34435f",
            command=self.test_voice,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            footer,
            text="Cancel",
            height=42,
            width=96,
            corner_radius=12,
            fg_color="#253149",
            hover_color="#34435f",
            command=self.destroy,
        ).grid(row=0, column=1, padx=(8, 8))

        ctk.CTkButton(
            footer,
            text="Save",
            height=42,
            width=110,
            corner_radius=12,
            fg_color="#1477ff",
            hover_color="#2491ff",
            command=self.save_settings,
        ).grid(row=0, column=2)

    def _add_switch(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
    ) -> ctk.CTkSwitch:
        """Add a labeled switch row."""
        ctk.CTkLabel(
            parent,
            text=label,
            font=("Segoe UI", 13, "bold"),
            text_color="#f8fbff",
            anchor="w",
        ).grid(row=row, column=0, padx=16, pady=12, sticky="w")

        switch = ctk.CTkSwitch(parent, text="")
        switch.grid(row=row, column=1, padx=16, pady=12, sticky="w")
        return switch

    def _add_option(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        variable: ctk.StringVar,
        values: list[str],
    ) -> ctk.CTkOptionMenu:
        """Add a labeled option menu row."""
        ctk.CTkLabel(
            parent,
            text=label,
            font=("Segoe UI", 13, "bold"),
            text_color="#f8fbff",
            anchor="w",
        ).grid(row=row, column=0, padx=16, pady=12, sticky="w")

        option = ctk.CTkOptionMenu(
            parent,
            variable=variable,
            values=values or ["Default"],
            fg_color="#101827",
            button_color="#1477ff",
            button_hover_color="#2491ff",
        )
        option.grid(row=row, column=1, padx=16, pady=12, sticky="ew")
        return option

    def _add_entry(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        placeholder: str,
    ) -> ctk.CTkEntry:
        """Add a labeled entry row."""
        ctk.CTkLabel(
            parent,
            text=label,
            font=("Segoe UI", 13, "bold"),
            text_color="#f8fbff",
            anchor="w",
        ).grid(row=row, column=0, padx=16, pady=12, sticky="w")

        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            height=38,
            corner_radius=10,
            fg_color="#101827",
            border_color="#2a3b58",
        )
        entry.grid(row=row, column=1, padx=16, pady=12, sticky="ew")
        return entry

    def _add_slider(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        variable: tk.Variable,
        from_value: float,
        to_value: float,
        label_variable: ctk.StringVar,
        command,
    ) -> None:
        """Add a labeled slider row."""
        label_frame = ctk.CTkFrame(parent, fg_color="transparent")
        label_frame.grid(row=row, column=0, padx=16, pady=12, sticky="ew")

        ctk.CTkLabel(
            label_frame,
            text=label,
            font=("Segoe UI", 13, "bold"),
            text_color="#f8fbff",
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            label_frame,
            textvariable=label_variable,
            font=("Segoe UI", 11),
            text_color="#8ea4c8",
            anchor="w",
        ).pack(anchor="w")

        slider = ctk.CTkSlider(
            parent,
            from_=from_value,
            to=to_value,
            variable=variable,
            command=command,
            progress_color="#1477ff",
            button_color="#38c7ff",
            button_hover_color="#8be9ff",
        )
        slider.grid(row=row, column=1, padx=16, pady=12, sticky="ew")

    def _load_voice_names(self) -> list[str]:
        """Load installed voice names."""
        voices = self.voice_manager.get_available_voices()

        self._voice_name_to_id = {
            voice["name"]: voice["id"]
            for voice in voices
            if voice.get("name") and voice.get("id")
        }

        return list(self._voice_name_to_id.keys()) or ["Default"]

    def _load_values(self) -> None:
        """Load saved values into controls."""
        settings = self.voice_manager.settings

        self._set_switch(self.voice_enabled, bool(settings.get("voice_enabled", True)))
        self._set_switch(self.auto_speaking, bool(settings.get("auto_speaking", True)))
        self._set_switch(self.auto_send_voice, bool(settings.get("auto_send_voice", False)))
        self._set_switch(self.wake_word_enabled, bool(settings.get("wake_word_enabled", True)))

        language_code = str(settings.get("language", "en"))
        self.language_var.set(VoiceLanguage.get_label(language_code))

        saved_voice_id = settings.get("voice_id")
        saved_voice_name = self._voice_name_from_id(saved_voice_id)
        self.voice_var.set(saved_voice_name or "Default")

        self.wake_word.delete(0, tk.END)
        self.wake_word.insert(0, str(settings.get("wake_word", "hey ayra")))

        self.speed_var.set(int(settings.get("speech_rate", 170)))
        self.volume_var.set(float(settings.get("volume", 1.0)))

        self._update_speed_label(self.speed_var.get())
        self._update_volume_label(self.volume_var.get())

    def _set_switch(self, switch: ctk.CTkSwitch, enabled: bool) -> None:
        """Set switch state."""
        if enabled:
            switch.select()
        else:
            switch.deselect()

    def _voice_name_from_id(self, voice_id: object) -> str | None:
        """Find voice name by voice ID."""
        if not voice_id:
            return None

        for name, item_id in self._voice_name_to_id.items():
            if item_id == voice_id:
                return name

        return None

    def _language_code_from_label(self, label: str) -> str:
        """Convert language label back to code."""
        for code, option_label in VoiceLanguage.choices():
            if option_label == label:
                return code

        return "en"

    def _update_speed_label(self, value: float) -> None:
        """Update speed display."""
        self.speed_label_var.set(str(int(float(value))))

    def _update_volume_label(self, value: float) -> None:
        """Update volume display."""
        self.volume_label_var.set(f"{int(float(value) * 100)}%")

    def test_voice(self) -> None:
        """Speak a test line with current saved engine."""
        self.voice_manager.speak("Hello Ashish, I am AYRA. Voice settings are ready.")

    def save_settings(self) -> None:
        """Save settings to VoiceManager."""
        selected_voice_name = self.voice_var.get()
        selected_voice_id = self._voice_name_to_id.get(selected_voice_name, "")

        self.voice_manager.save_settings(
            voice_enabled=bool(self.voice_enabled.get()),
            auto_speaking=bool(self.auto_speaking.get()),
            auto_send_voice=bool(self.auto_send_voice.get()),
            wake_word_enabled=bool(self.wake_word_enabled.get()),
            language=self._language_code_from_label(self.language_var.get()),
            wake_word=self.wake_word.get().strip() or "hey ayra",
            speech_rate=int(self.speed_var.get()),
            volume=float(self.volume_var.get()),
            voice_id=selected_voice_id,
        )
        self.destroy()