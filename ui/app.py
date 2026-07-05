import tkinter as tk
import customtkinter as ctk

from ai.assistant import AyraAssistant
from config.settings import AppSettings
from database.chat_db import ChatStore
from ui.chat import ChatPanel

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AyraApp(ctk.CTk):
    """Modern desktop-style assistant application."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Ayra AI")
        self.geometry("1280x780")
        self.minsize(980, 680)

        self.settings = AppSettings()
        self.assistant = AyraAssistant()
        self.store = ChatStore()

        self.configure(fg_color=("#f5f7fb", "#0f1117"))
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_area()
        if self.settings.is_gemini_configured:
            self.status_var.set("● Online")
        else:
            self.status_var.set("● Needs API key")

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=260, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(4, weight=1)

        title = ctk.CTkLabel(
            sidebar,
            text="Ayra AI",
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        )
        title.pack(padx=20, pady=(24, 6), anchor="w")

        subtitle = ctk.CTkLabel(
            sidebar,
            text="Your intelligent desktop assistant",
            font=("Segoe UI", 11),
            text_color=("#6b7280", "#9ca3af"),
            anchor="w",
        )
        subtitle.pack(padx=20, pady=(0, 20), anchor="w")

        self.status_var = ctk.StringVar(value="● Online")
        status = ctk.CTkLabel(
            sidebar,
            textvariable=self.status_var,
            font=("Segoe UI", 13, "bold"),
            text_color=("#22c55e", "#4ade80"),
            anchor="w",
        )
        status.pack(padx=20, pady=(0, 24), anchor="w")

        features = [
            "AI Chat",
            "Voice Commands",
            "Windows Automation",
            "Weather & News",
            "File & Folder Tools",
        ]
        for item in features:
            ctk.CTkButton(
                sidebar,
                text=item,
                height=38,
                fg_color="transparent",
                border_width=1,
                border_color=("#dbe4f0", "#2c313b"),
                hover_color=("#eaf2ff", "#1f2937"),
            ).pack(padx=18, pady=6, fill="x")

        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=16, pady=16)

        self.theme_btn = ctk.CTkButton(
            bottom,
            text="☀️ Light Mode",
            command=self.toggle_theme,
        )
        self.theme_btn.pack(fill="x", pady=(0, 6))

        ctk.CTkButton(
            bottom,
            text="⚙️ Settings",
            fg_color="transparent",
            border_width=1,
            border_color=("#dbe4f0", "#2c313b"),
        ).pack(fill="x")

    def _build_main_area(self) -> None:
        main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        self.chat_panel = ChatPanel(main, self.assistant, self.store)
        self.chat_panel.grid(row=0, column=0, sticky="nsew")

    def toggle_theme(self) -> None:
        current = ctk.get_appearance_mode().lower()
        new_mode = "light" if current == "dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        self.theme_btn.configure(text="🌙 Dark Mode" if new_mode == "light" else "☀️ Light Mode")

    def run(self) -> None:
        self.mainloop()