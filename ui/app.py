import customtkinter as ctk
from ai.openaiclient import ask_ai

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AyraApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Ayra AI")
        self.geometry("1200x700")

        # Main Frame
        self.main = ctk.CTkFrame(self)
        self.main.pack(fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(self.main, height=60)
        header.pack(fill="x", padx=20, pady=(20, 10))

        title = ctk.CTkLabel(
            header,
            text="🤖 Ayra AI",
            font=("Segoe UI", 24, "bold")
        )
        title.pack(side="left", padx=20)

        status = ctk.CTkLabel(
            header,
            text="🟢 Online",
            font=("Segoe UI", 14)
        )
        status.pack(side="right", padx=20)

        # Chat Box
        self.chat_box = ctk.CTkTextbox(
            self.main,
            font=("Segoe UI", 15)
        )
        self.chat_box.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=10
        )

        self.chat_box.insert(
            "end",
            """
👋 Welcome Ashu!

I'm Ayra AI.

I can help you with:

• AI Chat
• Coding
• Voice Commands
• Windows Automation
• Weather
• News
• File Management

Type a message below or press 🎤.

"""
        )

        # Bottom
        bottom = ctk.CTkFrame(self.main)
        bottom.pack(fill="x", padx=20, pady=20)

        self.entry = ctk.CTkEntry(
            bottom,
            placeholder_text="Ask Ayra anything...",
            height=45,
            corner_radius=15
        )
        self.entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10)
        )
        self.entry.bind("<Return>", lambda event: self.send_message())

        self.voice_btn = ctk.CTkButton(
            bottom,
            text="🎤",
            width=55,
            corner_radius=15,
            command=self.voice_input
        )
        self.voice_btn.pack(side="left", padx=(0, 10))

        self.send_btn = ctk.CTkButton(
            bottom,
            text="➤",
            width=60,
            corner_radius=15,
            command=self.send_message
        )
        self.send_btn.pack(side="left")

    def send_message(self):

        message = self.entry.get().strip()

        if not message:
            return

        self.chat_box.insert("end", f"\n👤 You: {message}\n")

        self.entry.delete(0, "end")

        self.update()

        try:
            reply = ask_ai(message)
        except Exception as e:
            reply = f"Error: {e}"

        self.chat_box.insert("end", f"🤖 Ayra: {reply}\n\n")

        self.chat_box.see("end")

    def voice_input(self):
        self.chat_box.insert("end", "\n🎤 Listening...\n")
        self.chat_box.see("end")

    def run(self):
        self.mainloop()