import tkinter as tk
import customtkinter as ctk

from voice.voice_manager import VoiceManager


class VoiceSettingsWindow(ctk.CTkToplevel):
    """Settings window for voice preferences."""

    def __init__(self, voice_manager: VoiceManager) -> None:
        super().__init__()
        self.title("Voice Settings")
        self.geometry("500x520")
        self.voice_manager = voice_manager
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Voice Settings", font=("Segoe UI", 20, "bold")).grid(
            row=0, column=0, padx=20, pady=(20, 10), sticky="w"
        )

        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text="Enable Voice").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.voice_enabled = ctk.CTkSwitch(frame, text="")
        self.voice_enabled.grid(row=0, column=1, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(frame, text="Auto Speaking").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.auto_speaking = ctk.CTkSwitch(frame, text="")
        self.auto_speaking.grid(row=1, column=1, padx=10, pady=8, sticky="w")

        ctk.CTkLabel(frame, text="Language").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        self.language_var = ctk.StringVar(value=self.voice_manager.settings.get("language", "en"))
        self.language_box = ctk.CTkOptionMenu(frame, variable=self.language_var, values=["en", "hi", "or"])
        self.language_box.grid(row=2, column=1, padx=10, pady=8, sticky="ew")

        ctk.CTkLabel(frame, text="Voice").grid(row=3, column=0, padx=10, pady=8, sticky="w")
        self.voice_var = ctk.StringVar(value=self.voice_manager.settings.get("voice_id", ""))
        voices = self.voice_manager.get_available_voices()
        voice_names = [voice["name"] for voice in voices]
        voice_ids = [voice["id"] for voice in voices]
        self.voice_box = ctk.CTkOptionMenu(frame, variable=self.voice_var, values=voice_names or ["Default"])
        self.voice_box.grid(row=3, column=1, padx=10, pady=8, sticky="ew")
        self._voice_ids = voice_ids

        ctk.CTkLabel(frame, text="Wake Word").grid(row=4, column=0, padx=10, pady=8, sticky="w")
        self.wake_word = ctk.CTkEntry(frame)
        self.wake_word.grid(row=4, column=1, padx=10, pady=8, sticky="ew")
        self.wake_word.insert(0, self.voice_manager.settings.get("wake_word", "hey ayra"))

        ctk.CTkLabel(frame, text="Speech Speed").grid(row=5, column=0, padx=10, pady=8, sticky="w")
        self.speed_var = ctk.IntVar(value=int(self.voice_manager.settings.get("speech_rate", 170)))
        self.speed_slider = ctk.CTkSlider(frame, from_=80, to=300, variable=self.speed_var)
        self.speed_slider.grid(row=5, column=1, padx=10, pady=8, sticky="ew")

        ctk.CTkLabel(frame, text="Volume").grid(row=6, column=0, padx=10, pady=8, sticky="w")
        self.volume_var = ctk.DoubleVar(value=float(self.voice_manager.settings.get("volume", 1.0)))
        self.volume_slider = ctk.CTkSlider(frame, from_=0.0, to=1.0, variable=self.volume_var)
        self.volume_slider.grid(row=6, column=1, padx=10, pady=8, sticky="ew")

        ctk.CTkButton(self, text="Save", command=self.save_settings).grid(row=2, column=0, padx=20, pady=20)

        self.voice_enabled.select() if self.voice_manager.settings.get("voice_enabled", True) else self.voice_enabled.deselect()
        self.auto_speaking.select() if self.voice_manager.settings.get("auto_speaking", True) else self.auto_speaking.deselect()

    def save_settings(self) -> None:
        selected_voice = ""
        if self.voice_var.get() and self._voice_ids:
            index = self.voice_box.cget("values").index(self.voice_var.get())
            if index < len(self._voice_ids):
                selected_voice = self._voice_ids[index]
        self.voice_manager.save_settings(
            voice_enabled=bool(self.voice_enabled.get()),
            auto_speaking=bool(self.auto_speaking.get()),
            language=self.language_var.get(),
            wake_word=self.wake_word.get().strip() or "hey ayra",
            speech_rate=self.speed_var.get(),
            volume=self.volume_var.get(),
            voice_id=selected_voice,
        )
        self.destroy()
