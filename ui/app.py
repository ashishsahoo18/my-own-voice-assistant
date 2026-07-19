"""Main desktop shell for AYRA AI."""

from __future__ import annotations

import customtkinter as ctk

from ai.assistant import AyraAssistant
from config.settings import AppSettings
from database.chat_db import ChatStore
from ui.chat import ChatPanel
from ui.setting import VoiceSettingsWindow
from voice.voice_manager import VoiceManager


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AyraApp(ctk.CTk):
    """Premium desktop AI assistant application shell."""

    def __init__(self) -> None:
        super().__init__()

        self.title("AYRA AI")
        self.geometry("1440x860")
        self.minsize(1180, 720)

        self.settings = AppSettings()
        self.assistant = AyraAssistant()
        self.store = ChatStore()
        self.voice_manager = VoiceManager()

        self.status_var = ctk.StringVar(value="ONLINE")
        self.ai_state_var = ctk.StringVar(value="READY")
        self.theme_var = ctk.StringVar(value="Dark Mode")

        self._configure_window()
        self._build_layout()
        self._update_startup_status()

    def _configure_window(self) -> None:
        """Configure the root window grid and theme colors."""
        self.configure(fg_color="#070b14")

        self.grid_columnconfigure(0, minsize=300, weight=0)
        self.grid_columnconfigure(1, minsize=420, weight=1)
        self.grid_columnconfigure(2, minsize=430, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _build_layout(self) -> None:
        """Build the three-panel AYRA AI interface."""
        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        """Build the system dashboard and shortcut panel."""
        self.left_panel = ctk.CTkFrame(
            self,
            fg_color="#0d1320",
            corner_radius=0,
            border_width=1,
            border_color="#172033",
        )
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(24, 18))

        title = ctk.CTkLabel(
            header,
            text="AYRA AI",
            font=("Segoe UI", 28, "bold"),
            text_color="#f8fbff",
            anchor="w",
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header,
            text="Futuristic desktop control center",
            font=("Segoe UI", 12),
            text_color="#8ea4c8",
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(4, 0))

        status = ctk.CTkLabel(
            header,
            textvariable=self.status_var,
            font=("Segoe UI", 13, "bold"),
            text_color="#38f7a6",
            anchor="w",
        )
        status.pack(anchor="w", pady=(16, 0))

        self._build_dashboard_card()
        self._build_shortcuts_card()

        bottom = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=18)

        self.theme_btn = ctk.CTkButton(
            bottom,
            textvariable=self.theme_var,
            height=40,
            corner_radius=10,
            fg_color="#1477ff",
            hover_color="#2491ff",
            command=self.toggle_theme,
        )
        self.theme_btn.pack(fill="x", pady=(0, 8))

        settings_btn = ctk.CTkButton(
            bottom,
            text="Settings",
            height=40,
            corner_radius=10,
            fg_color="#111a2b",
            hover_color="#1a2740",
            border_width=1,
            border_color="#26354f",
            command=self.open_voice_settings,
        )
        settings_btn.pack(fill="x")

    def _build_dashboard_card(self) -> None:
        """Build static dashboard rows. Live metrics will be added next."""
        card = ctk.CTkFrame(
            self.left_panel,
            fg_color="#101827",
            corner_radius=18,
            border_width=1,
            border_color="#1d2a40",
        )
        card.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkLabel(
            card,
            text="SYSTEM DASHBOARD",
            font=("Segoe UI", 12, "bold"),
            text_color="#5bbcff",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 10))

        metrics = [
            ("CPU", "Loading"),
            ("RAM", "Loading"),
            ("GPU", "Not available"),
            ("Disk", "Loading"),
            ("Internet", "Ready"),
            ("Battery", "Checking"),
            ("Temp", "N/A"),
            ("Time", "--:--"),
            ("Date", "--"),
        ]

        self.metric_labels: dict[str, ctk.CTkLabel] = {}

        for label, value in metrics:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=5)

            ctk.CTkLabel(
                row,
                text=label,
                font=("Segoe UI", 12),
                text_color="#93a4bf",
                anchor="w",
            ).pack(side="left")

            value_label = ctk.CTkLabel(
                row,
                text=value,
                font=("Segoe UI", 12, "bold"),
                text_color="#f8fbff",
                anchor="e",
            )
            value_label.pack(side="right")

            self.metric_labels[label] = value_label

    def _build_shortcuts_card(self) -> None:
        """Build quick desktop shortcut buttons."""
        card = ctk.CTkFrame(
            self.left_panel,
            fg_color="#101827",
            corner_radius=18,
            border_width=1,
            border_color="#1d2a40",
        )
        card.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkLabel(
            card,
            text="QUICK SHORTCUTS",
            font=("Segoe UI", 12, "bold"),
            text_color="#5bbcff",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 10))

        shortcuts = [
            "Browser",
            "VS Code",
            "Explorer",
            "Settings",
            "Notepad",
            "Calculator",
        ]

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(0, 14))
        grid.grid_columnconfigure((0, 1), weight=1)

        for index, name in enumerate(shortcuts):
            button = ctk.CTkButton(
                grid,
                text=name,
                height=38,
                corner_radius=10,
                fg_color="#0b1220",
                hover_color="#17345d",
                border_width=1,
                border_color="#24344d",
                command=lambda item=name: self._handle_shortcut(item),
            )
            button.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=4,
                pady=4,
            )

    def _build_center_panel(self) -> None:
        """Build the central AI avatar/orb area."""
        self.center_panel = ctk.CTkFrame(
            self,
            fg_color="#080d18",
            corner_radius=0,
            border_width=1,
            border_color="#111a2b",
        )
        self.center_panel.grid(row=0, column=1, sticky="nsew", padx=(1, 1))
        self.center_panel.grid_columnconfigure(0, weight=1)
        self.center_panel.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.center_panel,
            text="HEY, I'M AYRA",
            font=("Segoe UI", 34, "bold"),
            text_color="#f8fbff",
        ).grid(row=0, column=0, pady=(44, 4))

        ctk.CTkLabel(
            self.center_panel,
            text="AI chat • voice • automation • system control",
            font=("Segoe UI", 13),
            text_color="#8ea4c8",
        ).grid(row=1, column=0)

        orb_wrap = ctk.CTkFrame(
            self.center_panel,
            fg_color="transparent",
        )
        orb_wrap.grid(row=2, column=0, sticky="nsew", padx=28, pady=24)
        orb_wrap.grid_columnconfigure(0, weight=1)
        orb_wrap.grid_rowconfigure(0, weight=1)

        self.orb_canvas = ctk.CTkCanvas(
            orb_wrap,
            width=360,
            height=360,
            bg="#080d18",
            highlightthickness=0,
        )
        self.orb_canvas.grid(row=0, column=0)

        self._orb_phase = 0
        self._draw_orb()

        ctk.CTkLabel(
            self.center_panel,
            textvariable=self.ai_state_var,
            font=("Segoe UI", 18, "bold"),
            text_color="#38c7ff",
        ).grid(row=3, column=0, pady=(0, 8))

        ctk.CTkLabel(
            self.center_panel,
            text="Say “Hey Ayra” or type a command to begin.",
            font=("Segoe UI", 12),
            text_color="#7d8da8",
        ).grid(row=4, column=0, pady=(0, 34))

    def _build_right_panel(self) -> None:
        """Build the conversation panel."""
        self.right_panel = ctk.CTkFrame(
            self,
            fg_color="#0b101c",
            corner_radius=0,
            border_width=1,
            border_color="#172033",
        )
        self.right_panel.grid(row=0, column=2, sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(0, weight=1)

        self.chat_panel = ChatPanel(
            self.right_panel,
            self.assistant,
            self.store,
            self.voice_manager,
        )
        self.chat_panel.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

    def _draw_orb(self) -> None:
        """Draw and animate the glowing AYRA orb."""
        self.orb_canvas.delete("all")

        size = 360
        center = size // 2
        pulse = (self._orb_phase % 24) * 2
        glow = 24 + pulse

        self.orb_canvas.create_oval(
            center - 138 - glow,
            center - 138 - glow,
            center + 138 + glow,
            center + 138 + glow,
            outline="#0b7cff",
            width=2,
        )
        self.orb_canvas.create_oval(
            center - 120,
            center - 120,
            center + 120,
            center + 120,
            fill="#08182c",
            outline="#2fb7ff",
            width=4,
        )
        self.orb_canvas.create_oval(
            center - 82,
            center - 82,
            center + 82,
            center + 82,
            fill="#0d2b55",
            outline="#38f7ff",
            width=3,
        )
        self.orb_canvas.create_oval(
            center - 42,
            center - 42,
            center + 42,
            center + 42,
            fill="#38c7ff",
            outline="#b6f3ff",
            width=2,
        )
        self.orb_canvas.create_text(
            center,
            center,
            text="AYRA",
            fill="#f8fbff",
            font=("Segoe UI", 18, "bold"),
        )

        self._orb_phase += 1
        self.after(90, self._draw_orb)

    def _handle_shortcut(self, name: str) -> None:
        """Route shortcut clicks into the chat panel for now."""
        self.ai_state_var.set("THINKING")
        if hasattr(self.chat_panel, "add_assistant_message"):
            self.chat_panel.add_assistant_message(f"Opening {name}...")
        else:
            print(f"[AYRA AI] Shortcut selected: {name}")
        self.after(800, lambda: self.ai_state_var.set("READY"))

    def _update_startup_status(self) -> None:
        """Update startup status based on Gemini configuration."""
        if self.settings.is_gemini_configured:
            self.status_var.set("● ONLINE")
        else:
            self.status_var.set("● NEEDS API KEY")

    def open_voice_settings(self) -> None:
        """Open the voice settings window."""
        VoiceSettingsWindow(self.voice_manager)

    def toggle_theme(self) -> None:
        """Toggle between dark and light appearance modes."""
        current = ctk.get_appearance_mode().lower()
        new_mode = "light" if current == "dark" else "dark"

        ctk.set_appearance_mode(new_mode)
        self.theme_var.set("Dark Mode" if new_mode == "light" else "Light Mode")

    def run(self) -> None:
        """Run the application event loop."""
        self.mainloop()