import time
import customtkinter as ctk
from ai.assistant import AyraAssistant
from database.chat_db import ChatStore
from ui.chat import ChatPanel
from voice.voice_manager import VoiceManager

app = ctk.CTk()
app.withdraw()

assistant = AyraAssistant()
store = ChatStore()
voice_manager = VoiceManager()

chat_panel = ChatPanel(app, assistant, store, voice_manager)

print("--- Testing send_text_message ---")
chat_panel.send_text_message("What is Python?")
print("Children in chat_frame immediately after user send_text_message:", len(chat_panel.chat_frame.winfo_children()))

# Wait a moment for background thread AI reply
time.sleep(1.0)
app.update()

print("Children in chat_frame after AI reply:", len(chat_panel.chat_frame.winfo_children()))

for i, child in enumerate(chat_panel.chat_frame.winfo_children()):
    print(f"Child {i}: {type(child)}")
    for sub in child.winfo_children():
        print(f"  Sub: {type(sub)}")
        for sub2 in sub.winfo_children():
            print(f"    Sub2: {type(sub2)}")
            if hasattr(sub2, "cget"):
                try:
                    print(f"      Text: {sub2.cget('text')}")
                except Exception:
                    pass

print("\n--- Testing Current Time ---")
res_time = assistant.handle("What is the current time?")
print("Time response:", res_time)

print("\n--- Testing Computer Science ---")
res_cs = assistant.handle("what is basic knowledge of computer science")
print("CS response:", res_cs)

app.destroy()
