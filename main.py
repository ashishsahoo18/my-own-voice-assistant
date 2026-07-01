import speech_recognition as sr
import pyttsx3
import datetime
import webbrowser
from gtts import gTTS
from playsound import playsound
from dotenv import load_dotenv
import os
import wikipedia
import pywhatkit
import pyjokes
import requests
import csv
import time


try:
    import google.generativeai as genai
except ImportError:
    genai = None

# ===============================
# 🔐 PUT YOUR NEW GEMINI API KEY
# ===============================
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if genai and GEMINI_API_KEY != "":
    genai.configure(api_key=GEMINI_API_KEY)

    assistant_personality = """
    You are a smart female AI assistant.
    Keep responses short, natural, and friendly.
    Do not give long answers.
    Speak like a real human assistant.
    """

    model = genai.GenerativeModel(
        model_name='gemini-1.5-flash',
        system_instruction=assistant_personality
    )
else:
    model = None

# ===============================
# 🔊 VOICE SETUP
# ===============================
engine = pyttsx3.init()
recognizer = sr.Recognizer()

voices = engine.getProperty("voices")
if len(voices) > 1:
    engine.setProperty("voice", voices[1].id)

engine.setProperty('rate', 160)

def speak(text):
    print("Assistant:", text)
    engine.say(text)
    engine.runAndWait()

# ===============================
# 📱 LOAD CONTACTS
# ===============================
def load_contacts():
    contacts = {}
    try:
        with open("contacts.csv", "r") as file:
            reader = csv.DictReader(file)
            for row in reader:
                contacts[row["name"].lower()] = row["number"]
    except:
        pass
    return contacts

contacts = load_contacts()
#  ---listen() function----
def listen():
    try:
        with sr.Microphone() as source:
            print("Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=5)

        command = recognizer.recognize_google(
            audio,
            language="or-IN"
        )

        print("User:", command)
        return command.lower()

    except sr.UnknownValueError:
        return ""

    except Exception as e:
        print(e)
        return ""

# ===============================
# 📱 SMART WHATSAPP
# ===============================
def send_whatsapp(query):
    for name in contacts:
        if name in query:
            number = contacts[name]

            if "saying" in query:
                message = query.split("saying")[-1].strip()
            else:
                speak("What should I say?")
                message = listen()

            speak(f"Sending message to {name}")
            webbrowser.open("https://web.whatsapp.com")
            time.sleep(10)

            try:
                pywhatkit.sendwhatmsg_instantly(number, message, wait_time=15)
                speak("Message sent")
            except:
                speak("Failed to send message")
            return

    speak("Contact not found")

def speak(text):

    print("Assistant:", text)

    language = "or"

    if any("\u0B00" <= c <= "\u0B7F" for c in text):
        language = "or"
    else:
        language = "en"


    voice = gTTS(
        text=text,
        lang=language
    )

    voice.save("voice.mp3")

    playsound("voice.mp3")

    os.remove("voice.mp3")

# ===============================
# ⚙️ COMMAND HANDLER
# ===============================
def process_command(query):

    if "time" in query:
        speak(datetime.datetime.now().strftime("%I:%M %p"))

    elif "date" in query:
        speak(datetime.datetime.now().strftime("%d %B %Y"))

    elif "open youtube" in query:
        speak("Opening YouTube")
        webbrowser.open("https://youtube.com")

    elif "open google" in query:
        speak("Opening Google")
        webbrowser.open("https://google.com")

    elif "play" in query:
        song = query.replace("play", "")
        speak(f"Playing {song}")
        pywhatkit.playonyt(song)

    elif "joke" in query:
        speak(pyjokes.get_joke())

    elif "send" in query and "whatsapp" in query:
        send_whatsapp(query)

    elif "open" in query:
        app = query.replace("open", "").strip()
        os.system(f"start {app}")

    elif "shutdown" in query:
        speak("Shutting down")
        os.system("shutdown /s /t 1")

    elif "restart" in query:
        speak("Restarting")
        os.system("shutdown /r /t 1")

    elif "exit" in query or "stop" in query:
        speak("Goodbye")
        exit()

    # 🧠 Emotion detection
    elif "sad" in query or "tired" in query:
        speak("I understand. Want me to help you feel better?")

    else:
        speak(get_ai_response(query))

# ===============================
# 🔊 WAKE WORD SYSTEM
# ===============================
def run_assistant():
    speak("Assistant is ready. Say Hey Jarvis to start.")

    while True:
        query = listen()

        if "hey jarvis" in query:
            speak("Yes?")
            command = listen()

            if command:
                process_command(command)

# ===============================
# 🚀 START
# ===============================
if __name__ == "__main__":
    run_assistant()