import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AyraApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Ayra AI")
        self.geometry("1200x700")
        self.minsize(1000, 600)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=220)
        self.sidebar.pack(side="left", fill="y")

        ctk.CTkLabel(
            self.sidebar,
            text="🤖 Ayra AI",
            font=("Segoe UI", 26, "bold")
        ).pack(pady=30)

        buttons = [
            "🏠 Home",
            "💬 Chat",
            "🧠 Memory",
            "⚙ Settings"
        ]

        for text in buttons:
            ctk.CTkButton(
                self.sidebar,
                text=text,
                height=45
            ).pack(fill="x", padx=15, pady=8)

        # Main Area
        self.main = ctk.CTkFrame(self)
        self.main.pack(side="right", fill="both", expand=True)

        self.chat_box = ctk.CTkTextbox(
            self.main,
            font=("Segoe UI", 15)
        )
        self.chat_box.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=20
        )

        bottom = ctk.CTkFrame(self.main)
        bottom.pack(fill="x", padx=20, pady=15)

        self.entry = ctk.CTkEntry(
            bottom,
            placeholder_text="Type your message..."
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.voice_btn = ctk.CTkButton(
            bottom,
            text="🎤",
            width=55
        )
        self.voice_btn.pack(side="left", padx=(0, 10))

        self.send_btn = ctk.CTkButton(
            bottom,
            text="Send"
        )
        self.send_btn.pack(side="left")

    def run(self):
        self.mainloop()