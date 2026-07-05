import tkinter as tk
import customtkinter as ctk

from ai.assistant import AyraAssistant
from config.settings import AppSettings

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MessageBubble:
    """Render a single chat bubble in the UI."""

    def __init__(self, parent: ctk.CTkFrame, role: str, text: str) -> None:
        self.parent = parent
        self.role = role
        self.text = text
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="x", pady=8)

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


class AyraApp(ctk.CTk):
    """Modern desktop-style assistant application."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Ayra AI")
        self.geometry("1280x780")
        self.minsize(980, 680)

        self.settings = AppSettings()
        self.assistant = AyraAssistant()

        self.configure(fg_color=("#f5f7fb", "#0f1117"))
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_area()
        self._show_welcome_screen()
        if self.settings.is_gemini_configured:
            self.status_var.set("● Online")
        else:
            self.status_var.set("● Needs API key")
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
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, height=70, fg_color="transparent")
        header.grid(row=0, column=0, sticky="new", padx=20, pady=(20, 10))
        header.grid_columnconfigure(0, weight=1)

        self.header_title = ctk.CTkLabel(
            header,
            text="Good day, how can I help?",
            font=("Segoe UI", 22, "bold"),
            anchor="w",
        )
        self.header_title.grid(row=0, column=0, sticky="w")

        self.header_subtitle = ctk.CTkLabel(
            header,
            text="AI chat • voice • automation",
            font=("Segoe UI", 12),
            text_color=("#6b7280", "#9ca3af"),
            anchor="w",
        )
        self.header_subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.chat_frame = ctk.CTkScrollableFrame(main, fg_color="transparent")
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=20)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        input_bar = ctk.CTkFrame(main, fg_color="transparent")
        input_bar.grid(row=2, column=0, sticky="sew", padx=20, pady=20)
        input_bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            input_bar,
            placeholder_text="Ask Ayra anything...",
            height=46,
            corner_radius=18,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry.bind("<Return>", lambda event: self.send_message())

        self.voice_btn = ctk.CTkButton(
            input_bar,
            text="🎤",
            width=50,
            height=46,
            corner_radius=18,
            command=self.voice_input,
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

    def _show_welcome_screen(self) -> None:
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

    def toggle_theme(self) -> None:
        current = ctk.get_appearance_mode().lower()
        new_mode = "light" if current == "dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        self.theme_btn.configure(text="🌙 Dark Mode" if new_mode == "light" else "☀️ Light Mode")

    def send_message(self) -> None:
        message = self.entry.get().strip()
        if not message:
            return

        self._clear_welcome_if_present()
        MessageBubble(self.chat_frame, "user", message)
        self.entry.delete(0, tk.END)
        self.update_idletasks()

        try:
            reply = self.assistant.handle(message)
        except Exception as exc:
            reply = f"Sorry, I could not respond right now: {exc}"

        MessageBubble(self.chat_frame, "assistant", reply)
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    def voice_input(self) -> None:
        self._clear_welcome_if_present()
        MessageBubble(self.chat_frame, "assistant", "🎤 Listening for your voice command...")
        self.chat_frame._parent_canvas.yview_moveto(1.0)

    def _clear_welcome_if_present(self) -> None:
        for child in list(self.chat_frame.winfo_children()):
            if isinstance(child, ctk.CTkFrame):
                for grandchild in child.winfo_children():
                    if hasattr(grandchild, "cget") and grandchild.cget("text") == "👋 Welcome to Ayra AI":
                        child.destroy()
                        return

    def run(self) -> None:
        self.mainloop()