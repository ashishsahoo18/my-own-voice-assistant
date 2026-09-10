"""Main futuristic desktop shell for ASHISH AI."""

from __future__ import annotations

import math
import os
from datetime import datetime
import customtkinter as ctk

try:
    import psutil
except ImportError:
    psutil = None

from ai.assistant import AshishAssistant
from config.settings import AppSettings
from database.chat_db import ChatStore
from ui.chat import CommandConsolePanel
from ui.setting import VoiceSettingsWindow
from voice.voice_manager import VoiceManager


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ConfirmationModal(ctk.CTkToplevel):
    """Modal dialog for dangerous Windows commands confirmation."""

    def __init__(self, parent: ctk.CTk, title: str, message: str, on_confirm, on_cancel) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("480x240")
        self.resizable(False, False)
        self.configure(fg_color="#080e1e")

        self.on_confirm = on_confirm
        self.on_cancel = on_cancel

        self.transient(parent)
        self.grab_set()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Warning icon/title
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))

        ctk.CTkLabel(
            header,
            text="⚠️ SYSTEM SECURITY CONFIRMATION",
            font=("Segoe UI", 14, "bold"),
            text_color="#ff5555",
        ).pack(anchor="w")

        # Message
        ctk.CTkLabel(
            self,
            text=message,
            font=("Segoe UI", 13),
            text_color="#ffffff",
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, padx=24, pady=10, sticky="nw")

        # Action buttons
        button_bar = ctk.CTkFrame(self, fg_color="transparent")
        button_bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 20))
        button_bar.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            button_bar,
            text="CANCEL",
            height=42,
            corner_radius=10,
            fg_color="#1a263b",
            hover_color="#2c3b57",
            border_width=1,
            border_color="#3a4d70",
            font=("Segoe UI", 12, "bold"),
            command=self._cancel,
        ).grid(row=0, column=0, padx=(0, 8), sticky="ew")

        ctk.CTkButton(
            button_bar,
            text="CONFIRM",
            height=42,
            corner_radius=10,
            fg_color="#ff3b30",
            hover_color="#ff5e55",
            font=("Segoe UI", 12, "bold"),
            command=self._confirm,
        ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def _confirm(self) -> None:
        self.destroy()
        if self.on_confirm:
            self.on_confirm()

    def _cancel(self) -> None:
        self.destroy()
        if self.on_cancel:
            self.on_cancel()


class AshishApp(ctk.CTk):
    """Futuristic ASHISH AI Desktop Assistant Application Shell."""

    def __init__(self) -> None:
        super().__init__()

        self.title("ASHISH AI — Personal Windows Voice Assistant")
        self.geometry("1480x880")
        self.minsize(1200, 750)

        self.settings = AppSettings()
        self.assistant = AshishAssistant()
        self.store = ChatStore()
        self.voice_manager = VoiceManager()

        self.status_var = ctk.StringVar(value="SYSTEM ONLINE")
        self.ai_state_var = ctk.StringVar(value="READY")
        self.theme_var = ctk.StringVar(value="Dark Mode")

        self.current_state = "READY"

        self._configure_window()
        self._build_layout()
        self._start_system_monitoring()
        self._start_orb_animation()

    def _configure_window(self) -> None:
        self.configure(fg_color="#030712")

        # 3-column futuristic layout: Left Monitor (310px), Center Orb (flex), Right Console (450px)
        self.grid_columnconfigure(0, minsize=310, weight=0)
        self.grid_columnconfigure(1, minsize=420, weight=1)
        self.grid_columnconfigure(2, minsize=450, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _build_layout(self) -> None:
        self._build_left_panel()
        self._build_center_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        """Left System Monitor Panel."""
        self.left_panel = ctk.CTkFrame(
            self,
            fg_color="#060c19",
            corner_radius=0,
            border_width=1,
            border_color="#101c33",
        )
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_columnconfigure(0, weight=1)

        # Header
        header = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(22, 16))

        title = ctk.CTkLabel(
            header,
            text="ASHISH AI",
            font=("Segoe UI", 30, "bold"),
            text_color="#00d2ff",
            anchor="w",
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header,
            text="Windows AI Control Centre",
            font=("Segoe UI", 12),
            text_color="#6282b3",
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        status_indicator = ctk.CTkLabel(
            header,
            textvariable=self.status_var,
            font=("Segoe UI", 12, "bold"),
            text_color="#00ff9d",
            anchor="w",
        )
        status_indicator.pack(anchor="w", pady=(14, 0))

        # Real Live System Monitor Dashboard Card
        self._build_system_monitor_card()

        # Navigation / Action controls
        bottom = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=18, pady=18)

        settings_btn = ctk.CTkButton(
            bottom,
            text="⚙️  SETTINGS",
            height=44,
            corner_radius=12,
            fg_color="#0b172d",
            hover_color="#16294a",
            border_width=1,
            border_color="#1f3863",
            font=("Segoe UI", 12, "bold"),
            text_color="#00d2ff",
            command=self.open_voice_settings,
        )
        settings_btn.pack(fill="x")

    def _build_system_monitor_card(self) -> None:
        """Build System Monitor Card with real psutil updates."""
        card = ctk.CTkFrame(
            self.left_panel,
            fg_color="#091224",
            corner_radius=18,
            border_width=1,
            border_color="#152747",
        )
        card.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkLabel(
            card,
            text="SYSTEM MONITOR",
            font=("Segoe UI", 12, "bold"),
            text_color="#00d2ff",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 10))

        metrics = [
            ("CPU", "0%"),
            ("RAM", "0%"),
            ("BATTERY", "Checking"),
            ("NETWORK", "ONLINE"),
            ("SYSTEM", "STABLE"),
            ("TIME", "--:--"),
            ("DATE", "--"),
        ]

        self.metric_labels: dict[str, ctk.CTkLabel] = {}

        for label, default_val in metrics:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=5)

            ctk.CTkLabel(
                row,
                text=label,
                font=("Segoe UI", 11, "bold"),
                text_color="#718bb5",
                anchor="w",
            ).pack(side="left")

            val_label = ctk.CTkLabel(
                row,
                text=default_val,
                font=("Segoe UI", 12, "bold"),
                text_color="#ffffff",
                anchor="e",
            )
            val_label.pack(side="right")

            self.metric_labels[label] = val_label

    def _build_center_panel(self) -> None:
        """Center AI Orb and State Display."""
        self.center_panel = ctk.CTkFrame(
            self,
            fg_color="#040914",
            corner_radius=0,
            border_width=1,
            border_color="#0b172a",
        )
        self.center_panel.grid(row=0, column=1, sticky="nsew")
        self.center_panel.grid_columnconfigure(0, weight=1)
        self.center_panel.grid_rowconfigure(2, weight=1)

        # Title Header
        ctk.CTkLabel(
            self.center_panel,
            text="ASHISH AI",
            font=("Segoe UI", 36, "bold"),
            text_color="#ffffff",
        ).grid(row=0, column=0, pady=(40, 2))

        ctk.CTkLabel(
            self.center_panel,
            text="PARALLEL DESKTOP CONTROL ENGINE",
            font=("Segoe UI", 11, "bold"),
            text_color="#00d2ff"
        ).grid(row=1, column=0)

        # Orb canvas wrapper
        orb_wrap = ctk.CTkFrame(
            self.center_panel,
            fg_color="transparent",
        )
        orb_wrap.grid(row=2, column=0, sticky="nsew", padx=20, pady=20)
        orb_wrap.grid_columnconfigure(0, weight=1)
        orb_wrap.grid_rowconfigure(0, weight=1)

        self.orb_canvas = ctk.CTkCanvas(
            orb_wrap,
            width=380,
            height=380,
            bg="#040914",
            highlightthickness=0,
        )
        self.orb_canvas.grid(row=0, column=0)

        self._orb_phase = 0.0

        # State Indicator
        self.state_label = ctk.CTkLabel(
            self.center_panel,
            textvariable=self.ai_state_var,
            font=("Segoe UI", 22, "bold"),
            text_color="#00d2ff",
        )
        self.state_label.grid(row=3, column=0, pady=(0, 6))

        ctk.CTkLabel(
            self.center_panel,
            text="Speak or type a command to execute",
            font=("Segoe UI", 12),
            text_color="#516d99",
        ).grid(row=4, column=0, pady=(0, 36))

    def _build_right_panel(self) -> None:
        """Right Command Console Panel."""
        self.right_panel = ctk.CTkFrame(
            self,
            fg_color="#050a17",
            corner_radius=0,
            border_width=1,
            border_color="#101c33",
        )
        self.right_panel.grid(row=0, column=2, sticky="nsew")
        self.right_panel.grid_columnconfigure(0, weight=1)
        self.right_panel.grid_rowconfigure(0, weight=1)

        self.console_panel = CommandConsolePanel(
            self.right_panel,
            self.assistant,
            self.store,
            self.voice_manager,
            on_state_change=self.set_state,
            request_confirmation=self.show_confirmation_modal,
        )
        self.console_panel.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

    def set_state(self, state: str) -> None:
        """Update active AI orb state."""
        self.current_state = state
        self.ai_state_var.set(state.upper())
        if state == "READY":
            self.state_label.configure(text_color="#00d2ff")
        elif state == "LISTENING":
            self.state_label.configure(text_color="#00ff9d")
        elif state == "PROCESSING":
            self.state_label.configure(text_color="#ffcf36")
        elif state == "EXECUTING":
            self.state_label.configure(text_color="#ff36e8")
        elif state == "SPEAKING":
            self.state_label.configure(text_color="#36b6ff")
        elif state == "ERROR":
            self.state_label.configure(text_color="#ff4444")

    def show_confirmation_modal(self, message: str, on_confirm, on_cancel) -> None:
        """Show dangerous command confirmation modal dialog."""
        ConfirmationModal(
            self,
            title="ASHISH AI Security Confirmation",
            message=message,
            on_confirm=on_confirm,
            on_cancel=on_cancel,
        )

    def _start_orb_animation(self) -> None:
        """Animate multi-ring glowing futuristic ASHISH AI Orb."""
        self.orb_canvas.delete("all")

        size = 380
        cx, cy = size // 2, size // 2
        self._orb_phase += 0.08
        phase = self._orb_phase

        state = self.current_state

        # State pulse modifier
        if state == "LISTENING":
            pulse_r = math.sin(phase * 2.5) * 12
            color_outer = "#00ff9d"
            color_mid = "#00c473"
        elif state == "PROCESSING":
            pulse_r = math.sin(phase * 4.0) * 8
            color_outer = "#ffcf36"
            color_mid = "#e6b000"
        elif state == "EXECUTING":
            pulse_r = math.sin(phase * 5.0) * 16
            color_outer = "#ff36e8"
            color_mid = "#b800a3"
        elif state == "SPEAKING":
            pulse_r = math.sin(phase * 3.0) * 10
            color_outer = "#36b6ff"
            color_mid = "#0088cc"
        elif state == "ERROR":
            pulse_r = math.sin(phase * 6.0) * 14
            color_outer = "#ff4444"
            color_mid = "#cc0000"
        else:  # READY
            pulse_r = math.sin(phase) * 6
            color_outer = "#00d2ff"
            color_mid = "#0077b6"

        # Outer energy ring
        r_outer = 145 + pulse_r
        self.orb_canvas.create_oval(
            cx - r_outer,
            cy - r_outer,
            cx + r_outer,
            cy + r_outer,
            outline=color_outer,
            width=2,
        )

        # Concentric rotating HUD arcs
        for i in range(3):
            arc_r = 125 - i * 15
            start_angle = (phase * 40 * (i + 1)) % 360
            self.orb_canvas.create_arc(
                cx - arc_r,
                cy - arc_r,
                cx + arc_r,
                cy + arc_r,
                start=start_angle,
                extent=80,
                style="arc",
                outline=color_mid,
                width=3,
            )

        # Core glowing orb
        r_core = 75 + pulse_r * 0.4
        self.orb_canvas.create_oval(
            cx - r_core,
            cy - r_core,
            cx + r_core,
            cy + r_core,
            fill="#051833",
            outline=color_outer,
            width=3,
        )

        # Inner highlight
        r_inner = 35 + pulse_r * 0.2
        self.orb_canvas.create_oval(
            cx - r_inner,
            cy - r_inner,
            cx + r_inner,
            cy + r_inner,
            fill=color_outer,
            outline="#ffffff",
            width=2,
        )

        # Text label inside core
        self.orb_canvas.create_text(
            cx,
            cy,
            text="ASHISH",
            fill="#ffffff",
            font=("Segoe UI", 16, "bold"),
        )

        self.after(50, self._start_orb_animation)

    def _start_system_monitoring(self) -> None:
        """Poll real live system metrics via psutil."""
        try:
            if psutil:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                battery = psutil.sensors_battery()

                self.metric_labels["CPU"].configure(text=f"{cpu:.0f}%")
                self.metric_labels["RAM"].configure(text=f"{ram:.0f}%")

                if battery:
                    b_str = f"{battery.percent:.0f}% {'⚡' if battery.power_plugged else ''}"
                    self.metric_labels["BATTERY"].configure(text=b_str)
                else:
                    self.metric_labels["BATTERY"].configure(text="AC Power")
        except Exception:
            pass

        now = datetime.now()
        self.metric_labels["TIME"].configure(text=now.strftime("%I:%M %p"))
        self.metric_labels["DATE"].configure(text=now.strftime("%b %d, %Y"))

        self.after(1000, self._start_system_monitoring)

    def open_voice_settings(self) -> None:
        VoiceSettingsWindow(self.voice_manager)

    def run(self) -> None:
        self.mainloop()


# Alias for backward compatibility
AyraApp = AshishApp
