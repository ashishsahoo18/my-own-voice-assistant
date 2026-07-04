"""
main.py
Ayra Voice Assistant — single-file build.

This collapses the modular project (config/core/gui/commands/utils packages)
into one file. Functionality is identical to the modular version; only the
file layout changed. See README.md for why the modular layout is the better
default and what you give up by using this file instead.
"""

import ast
import operator
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
import logging

import cv2
import numpy as np
import psutil
import pyautogui
import pyttsx3
import requests
import speech_recognition as sr
import wikipedia
import customtkinter as ctk
from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APIError, AuthenticationError

# ============================================================================
# CONFIG
# ============================================================================

load_dotenv()


class Config:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "")
    WEATHER_DEFAULT_CITY: str = os.getenv("WEATHER_DEFAULT_CITY", "Bhubaneswar")

    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")

    ASSISTANT_NAME: str = os.getenv("ASSISTANT_NAME", "Ayra")
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en")

    WHATSAPP_DEFAULT_COUNTRY_CODE: str = os.getenv("WHATSAPP_DEFAULT_COUNTRY_CODE", "+91")

    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    LOG_DIR: str = os.path.join(BASE_DIR, "logs")
    MEMORY_FILE: str = os.path.join(BASE_DIR, "logs", "memory.json")

    LANGUAGE_CODES = {
        "en": "en-IN",
        "hi": "hi-IN",
        "od": "or-IN",
    }

    WAKE_WORDS = ["ayra", "आयरा", "ଆୟରା"]

    @staticmethod
    def validate():
        warnings = []
        if not Config.OPENAI_API_KEY:
            warnings.append("OPENAI_API_KEY is missing. GPT conversation will not work.")
        if not Config.WEATHER_API_KEY:
            warnings.append("WEATHER_API_KEY is missing. Weather command will fail gracefully.")
        if not Config.NEWS_API_KEY:
            warnings.append("NEWS_API_KEY is missing. News command will fail gracefully.")
        return warnings


os.makedirs(Config.LOG_DIR, exist_ok=True)

WORKSPACE_DIR = os.path.join(Config.BASE_DIR, "ayra_workspace")
SCREENSHOT_DIR = os.path.join(Config.BASE_DIR, "screenshots")
CAPTURE_DIR = os.path.join(Config.BASE_DIR, "captures")
IS_WINDOWS = platform.system() == "Windows"

# ============================================================================
# LOGGING
# ============================================================================

_loggers = {}


def get_logger(name: str) -> logging.Logger:
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    log_path = os.path.join(Config.LOG_DIR, "ayra.log")
    file_handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _loggers[name] = logger
    return logger


logger = get_logger("ayra")

# ============================================================================
# LANGUAGE / LOCALIZATION
# ============================================================================

STRINGS = {
    "greeting": {
        "en": "Hello, I am Ayra. How can I help you today?",
        "hi": "नमस्ते, मैं आयरा हूँ। मैं आपकी कैसे मदद कर सकती हूँ?",
        "od": "ନମସ୍କାର, ମୁଁ ଆୟରା। ମୁଁ ଆପଣଙ୍କୁ କିପରି ସାହାଯ୍ୟ କରିପାରିବି?",
    },
    "listening": {
        "en": "I'm listening.",
        "hi": "मैं सुन रही हूँ।",
        "od": "ମୁଁ ଶୁଣୁଛି।",
    },
    "not_understood": {
        "en": "Sorry, I did not catch that. Could you repeat?",
        "hi": "माफ़ कीजिए, मैं समझ नहीं पाई। कृपया दोहराएँ।",
        "od": "କ୍ଷମା କରନ୍ତୁ, ମୁଁ ବୁଝି ପାରିଲି ନାହିଁ।",
    },
    "no_internet": {
        "en": "I seem to be offline. I'll try to help using local commands only.",
        "hi": "लगता है इंटरनेट नहीं है। मैं केवल स्थानीय कमांड से मदद करने की कोशिश करूँगी।",
        "od": "ଇଣ୍ଟରନେଟ ନାହିଁ ପରି ଲାଗୁଛି। ମୁଁ ସ୍ଥାନୀୟ ନିର୍ଦ୍ଦେଶରେ ସାହାଯ୍ୟ କରିବି।",
    },
    "goodbye": {
        "en": "Goodbye. Call me anytime you need me.",
        "hi": "अलविदा। जब भी ज़रूरत हो, मुझे बुला लीजिएगा।",
        "od": "ବିଦାୟ। ଆବଶ୍ୟକତା ପଡ଼ିଲେ ମୋତେ ଡାକନ୍ତୁ।",
    },
    "error": {
        "en": "Something went wrong while doing that.",
        "hi": "यह करते समय कुछ गड़बड़ हो गई।",
        "od": "ଏହା କରିବା ସମୟରେ କିଛି ଭୁଲ ହେଲା।",
    },
}


def t(key: str, lang: str = None) -> str:
    lang = lang or Config.DEFAULT_LANGUAGE
    entry = STRINGS.get(key, {})
    return entry.get(lang, entry.get("en", key))


# ============================================================================
# MEMORY
# ============================================================================

import json


class Memory:
    def __init__(self, max_context_messages: int = 20):
        self.max_context_messages = max_context_messages
        self._lock = threading.Lock()
        self.history = []
        self._load()

    def _load(self):
        try:
            if os.path.exists(Config.MEMORY_FILE):
                with open(Config.MEMORY_FILE, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                logger.info("Loaded %d messages from memory file.", len(self.history))
            else:
                self.history = []
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load memory file, starting fresh: %s", exc)
            self.history = []

    def _save(self):
        try:
            with open(Config.MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.error("Failed to save memory file: %s", exc)

    def add(self, role: str, content: str):
        with self._lock:
            self.history.append(
                {
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                }
            )
            self._save()

    def get_context(self) -> list:
        with self._lock:
            recent = self.history[-self.max_context_messages :]
            return [{"role": m["role"], "content": m["content"]} for m in recent]

    def clear(self):
        with self._lock:
            self.history = []
            self._save()
        logger.info("Memory cleared.")


# ============================================================================
# VOICE INPUT
# ============================================================================

class VoiceInput:
    def __init__(self, language: str = None):
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.language = language or Config.DEFAULT_LANGUAGE
        self._microphone_available = True
        try:
            self.microphone = sr.Microphone()
        except OSError as exc:
            logger.error("No microphone detected: %s", exc)
            self.microphone = None
            self._microphone_available = False

    def set_language(self, language: str):
        if language in Config.LANGUAGE_CODES:
            self.language = language
        else:
            logger.warning("Unsupported language '%s', keeping '%s'.", language, self.language)

    def is_available(self) -> bool:
        return self._microphone_available

    def listen_once(self, timeout: int = 5, phrase_time_limit: int = 12) -> str:
        if not self._microphone_available:
            logger.warning("Microphone unavailable, cannot listen.")
            return ""

        lang_code = Config.LANGUAGE_CODES.get(self.language, "en-IN")

        try:
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_time_limit
                )
        except sr.WaitTimeoutError:
            return ""
        except OSError as exc:
            logger.error("Microphone read error: %s", exc)
            return ""

        try:
            text = self.recognizer.recognize_google(audio, language=lang_code)
            logger.info("Recognized speech: %s", text)
            return text.lower().strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            logger.error("Speech recognition service unavailable (offline?): %s", exc)
            return "__OFFLINE__"


# ============================================================================
# VOICE OUTPUT
# ============================================================================

class VoiceOutput:
    def __init__(self):
        self._lock = threading.Lock()
        self.is_speaking = False
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            self._engine = pyttsx3.init(driverName="sapi5")
        except Exception:
            try:
                self._engine = pyttsx3.init()
            except Exception as exc:
                logger.error("Failed to initialize TTS engine: %s", exc)
                self._engine = None
                return

        self._engine.setProperty("rate", 175)
        self._engine.setProperty("volume", 1.0)
        self._select_female_voice()

    def _select_female_voice(self):
        if not self._engine:
            return
        try:
            voices = self._engine.getProperty("voices")
            for voice in voices:
                name = (voice.name or "").lower()
                voice_id = (voice.id or "").lower()
                if "female" in name or "zira" in name or "female" in voice_id or "zira" in voice_id:
                    self._engine.setProperty("voice", voice.id)
                    logger.info("Selected female voice: %s", voice.name)
                    return
            if voices:
                index = 1 if len(voices) > 1 else 0
                self._engine.setProperty("voice", voices[index].id)
                logger.warning("No explicit female voice found, using voice index %d.", index)
        except Exception as exc:
            logger.error("Voice selection failed: %s", exc)

    def speak(self, text: str, on_word=None, on_done=None):
        if not text:
            if on_done:
                on_done()
            return

        thread = threading.Thread(
            target=self._speak_blocking, args=(text, on_word, on_done), daemon=True
        )
        thread.start()

    def _speak_blocking(self, text, on_word, on_done):
        with self._lock:
            if not self._engine:
                logger.error("TTS engine not initialized; cannot speak.")
                if on_done:
                    on_done()
                return

            self.is_speaking = True
            try:
                if on_word:
                    def word_callback(name, location, length):
                        try:
                            word = text[location : location + length]
                            on_word(word)
                        except Exception:
                            pass

                    self._engine.connect("started-word", word_callback)

                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as exc:
                logger.error("Error during speech synthesis: %s", exc)
            finally:
                self.is_speaking = False
                if on_done:
                    on_done()

    def stop(self):
        try:
            if self._engine:
                self._engine.stop()
        except Exception as exc:
            logger.error("Error stopping speech: %s", exc)
        self.is_speaking = False


# ============================================================================
# GPT ENGINE
# ============================================================================

SYSTEM_PROMPT = (
    "You are Ayra, a friendly, concise, and helpful voice assistant. "
    "Keep spoken responses natural and conversational, generally under "
    "60 words unless the user explicitly asks for detail. Avoid using "
    "markdown, bullet points, or formatting symbols since your replies "
    "are spoken aloud, not read."
)


class GPTEngine:
    def __init__(self, memory: Memory):
        self.memory = memory
        self._client = None
        if Config.OPENAI_API_KEY:
            try:
                self._client = OpenAI(api_key=Config.OPENAI_API_KEY)
            except Exception as exc:
                logger.error("Failed to initialize OpenAI client: %s", exc)
                self._client = None
        else:
            logger.warning("No OPENAI_API_KEY set; GPT conversation is disabled.")

    def is_available(self) -> bool:
        return self._client is not None

    def ask(self, user_text: str) -> str:
        if not self._client:
            return "I can't reach my language model right now because no API key is set."

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.memory.get_context())
        messages.append({"role": "user", "content": user_text})

        try:
            response = self._client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=messages,
                max_tokens=300,
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except AuthenticationError:
            logger.error("OpenAI authentication failed. Check OPENAI_API_KEY.")
            return "My API key seems to be invalid, so I can't think right now."
        except APIConnectionError:
            logger.error("OpenAI API connection failed (offline?).")
            return "__OFFLINE__"
        except APIError as exc:
            logger.error("OpenAI API error: %s", exc)
            return "I ran into a problem reaching my language model."
        except Exception as exc:
            logger.error("Unexpected GPT error: %s", exc)
            return "Something unexpected went wrong while I was thinking."


# ============================================================================
# FACE UI (OpenCV, threaded, mouth-synced)
# ============================================================================

WINDOW_NAME = "Ayra"
CANVAS_SIZE = 480
FACE_COLOR = (235, 206, 135)
EYE_COLOR = (40, 40, 40)
MOUTH_COLOR = (60, 60, 200)


class FaceUI:
    def __init__(self):
        self._running = False
        self._thread = None
        self.mouth_open = False
        self._lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._render_loop, daemon=True)
        self._thread.start()
        logger.info("Face UI thread started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        try:
            cv2.destroyWindow(WINDOW_NAME)
        except cv2.error:
            pass
        logger.info("Face UI thread stopped.")

    def set_mouth(self, is_open: bool):
        with self._lock:
            self.mouth_open = is_open

    def _render_loop(self):
        frame_count = 0
        blink_timer = 0
        while self._running:
            frame_count += 1
            blink_timer += 1

            canvas = np.full((CANVAS_SIZE, CANVAS_SIZE, 3), 30, dtype=np.uint8)
            center = (CANVAS_SIZE // 2, CANVAS_SIZE // 2)

            cv2.circle(canvas, center, 160, FACE_COLOR, -1, lineType=cv2.LINE_AA)
            cv2.circle(canvas, center, 160, (255, 255, 255), 2, lineType=cv2.LINE_AA)

            is_blinking = (blink_timer % 90) < 6

            eye_y = center[1] - 40
            for dx in (-55, 55):
                eye_center = (center[0] + dx, eye_y)
                if is_blinking:
                    cv2.line(
                        canvas,
                        (eye_center[0] - 18, eye_center[1]),
                        (eye_center[0] + 18, eye_center[1]),
                        EYE_COLOR,
                        4,
                        lineType=cv2.LINE_AA,
                    )
                else:
                    cv2.circle(canvas, eye_center, 18, (255, 255, 255), -1, lineType=cv2.LINE_AA)
                    cv2.circle(canvas, eye_center, 8, EYE_COLOR, -1, lineType=cv2.LINE_AA)

            with self._lock:
                mouth_open = self.mouth_open

            mouth_y = center[1] + 55
            if mouth_open:
                height = 22 + int(10 * abs(np.sin(frame_count * 0.6)))
                cv2.ellipse(
                    canvas,
                    (center[0], mouth_y),
                    (55, height),
                    0,
                    0,
                    360,
                    MOUTH_COLOR,
                    -1,
                    lineType=cv2.LINE_AA,
                )
            else:
                cv2.line(
                    canvas,
                    (center[0] - 45, mouth_y),
                    (center[0] + 45, mouth_y),
                    MOUTH_COLOR,
                    5,
                    lineType=cv2.LINE_AA,
                )

            cv2.putText(
                canvas,
                "AYRA",
                (center[0] - 55, CANVAS_SIZE - 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow(WINDOW_NAME, canvas)
            key = cv2.waitKey(33) & 0xFF
            if key == 27:
                break

        self._running = False


# ============================================================================
# SYSTEM COMMANDS
# ============================================================================

class SystemCommands:
    def __init__(self, screenshot_dir: str, capture_dir: str):
        self.screenshot_dir = screenshot_dir
        self.capture_dir = capture_dir
        os.makedirs(self.screenshot_dir, exist_ok=True)
        os.makedirs(self.capture_dir, exist_ok=True)

    def open_notepad(self) -> str:
        try:
            if IS_WINDOWS:
                subprocess.Popen(["notepad.exe"])
            else:
                subprocess.Popen(["gedit"])
            return "Opening Notepad."
        except Exception as exc:
            logger.error("Failed to open Notepad: %s", exc)
            return "I could not open Notepad."

    def open_chrome(self) -> str:
        try:
            if IS_WINDOWS:
                subprocess.Popen(["cmd", "/c", "start", "chrome"], shell=False)
            else:
                subprocess.Popen(["google-chrome"])
            return "Opening Chrome."
        except Exception as exc:
            logger.error("Failed to open Chrome: %s", exc)
            return "I could not open Chrome. Is it installed?"

    def open_vscode(self) -> str:
        try:
            if IS_WINDOWS:
                subprocess.Popen(["cmd", "/c", "code"], shell=False)
            else:
                subprocess.Popen(["code"])
            return "Opening Visual Studio Code."
        except Exception as exc:
            logger.error("Failed to open VS Code: %s", exc)
            return "I could not open VS Code. Make sure it's on your PATH."

    def shutdown(self) -> str:
        try:
            if IS_WINDOWS:
                os.system("shutdown /s /t 5")
            else:
                os.system("shutdown -h now")
            return "Shutting down in 5 seconds."
        except Exception as exc:
            logger.error("Shutdown command failed: %s", exc)
            return "I could not shut down the system."

    def restart(self) -> str:
        try:
            if IS_WINDOWS:
                os.system("shutdown /r /t 5")
            else:
                os.system("reboot")
            return "Restarting in 5 seconds."
        except Exception as exc:
            logger.error("Restart command failed: %s", exc)
            return "I could not restart the system."

    def sleep(self) -> str:
        try:
            if IS_WINDOWS:
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
            else:
                os.system("systemctl suspend")
            return "Putting the system to sleep."
        except Exception as exc:
            logger.error("Sleep command failed: %s", exc)
            return "I could not put the system to sleep."

    def set_volume(self, percent: int) -> str:
        percent = max(0, min(100, percent))
        if not IS_WINDOWS:
            return "Volume control is only implemented for Windows in this build."
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
            return f"Volume set to {percent} percent."
        except Exception as exc:
            logger.error("Volume control failed: %s", exc)
            return "I could not change the system volume."

    def mute(self) -> str:
        if not IS_WINDOWS:
            return "Mute is only implemented for Windows in this build."
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMute(1, None)
            return "Muted."
        except Exception as exc:
            logger.error("Mute failed: %s", exc)
            return "I could not mute the system."

    def take_screenshot(self) -> str:
        try:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path = os.path.join(self.screenshot_dir, filename)
            image = pyautogui.screenshot()
            image.save(path)
            return f"Screenshot saved as {filename}."
        except Exception as exc:
            logger.error("Screenshot failed: %s", exc)
            return "I could not take a screenshot."

    def capture_camera_photo(self) -> str:
        try:
            cam = cv2.VideoCapture(0, cv2.CAP_DSHOW if IS_WINDOWS else 0)
            if not cam.isOpened():
                return "I could not access the camera."
            for _ in range(5):
                cam.read()
                time.sleep(0.05)
            ret, frame = cam.read()
            cam.release()
            if not ret:
                return "I could not capture a photo."
            filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path = os.path.join(self.capture_dir, filename)
            cv2.imwrite(path, frame)
            return f"Photo captured and saved as {filename}."
        except Exception as exc:
            logger.error("Camera capture failed: %s", exc)
            return "Something went wrong accessing the camera."

    def battery_status(self) -> str:
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return "This device does not report battery information."
            plugged = "and it is charging" if battery.power_plugged else "and it is not charging"
            return f"Battery is at {round(battery.percent)} percent, {plugged}."
        except Exception as exc:
            logger.error("Battery check failed: %s", exc)
            return "I could not read the battery status."

    def internet_speed(self) -> str:
        try:
            import speedtest

            st = speedtest.Speedtest()
            st.get_best_server()
            download = st.download() / 1_000_000
            upload = st.upload() / 1_000_000
            return f"Download speed is {download:.1f} megabits per second, upload is {upload:.1f} megabits per second."
        except Exception as exc:
            logger.error("Speed test failed: %s", exc)
            return "I could not measure the internet speed. Please check your connection."


# ============================================================================
# WEB COMMANDS
# ============================================================================

class WebCommands:
    def google_search(self, query: str) -> str:
        import webbrowser

        try:
            url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            webbrowser.open(url)
            return f"Searching Google for {query}."
        except Exception as exc:
            logger.error("Google search failed: %s", exc)
            return "I could not open the Google search."

    def youtube_search(self, query: str) -> str:
        import webbrowser

        try:
            import pywhatkit

            pywhatkit.playonyt(query)
            return f"Playing {query} on YouTube."
        except Exception as exc:
            logger.error("YouTube search failed: %s", exc)
            try:
                url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
                webbrowser.open(url)
                return f"Opened YouTube search results for {query}."
            except Exception as inner_exc:
                logger.error("YouTube fallback failed: %s", inner_exc)
                return "I could not search YouTube."

    def send_whatsapp_message(self, phone_number: str, message: str) -> str:
        try:
            import pywhatkit

            now = datetime.now()
            send_hour = now.hour
            send_minute = now.minute + 1
            if send_minute >= 60:
                send_minute -= 60
                send_hour = (send_hour + 1) % 24

            pywhatkit.sendwhatmsg(
                phone_number,
                message,
                send_hour,
                send_minute,
                wait_time=20,
                tab_close=True,
            )
            return f"Scheduled WhatsApp message to {phone_number}."
        except Exception as exc:
            logger.error("WhatsApp send failed: %s", exc)
            return "I could not send the WhatsApp message. Make sure WhatsApp Web is logged in."

    def wikipedia_summary(self, query: str, sentences: int = 2) -> str:
        try:
            wikipedia.set_lang("en")
            summary = wikipedia.summary(query, sentences=sentences, auto_suggest=True)
            return summary
        except wikipedia.exceptions.DisambiguationError as exc:
            options = ", ".join(exc.options[:5])
            return f"That's ambiguous. Did you mean: {options}?"
        except wikipedia.exceptions.PageError:
            return f"I could not find a Wikipedia page for {query}."
        except Exception as exc:
            logger.error("Wikipedia lookup failed: %s", exc)
            return "I could not reach Wikipedia right now."

    def get_weather(self, city: str = None) -> str:
        city = city or Config.WEATHER_DEFAULT_CITY
        if not Config.WEATHER_API_KEY:
            return "Weather is not configured. Please add a WEATHER_API_KEY in the .env file."
        try:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {"q": city, "appid": Config.WEATHER_API_KEY, "units": "metric"}
            response = requests.get(url, params=params, timeout=6)
            data = response.json()
            if response.status_code != 200:
                message = data.get("message", "unknown error")
                return f"I could not get the weather for {city}: {message}."
            temp = data["main"]["temp"]
            feels_like = data["main"]["feels_like"]
            description = data["weather"][0]["description"]
            return (
                f"It is currently {temp:.1f} degrees Celsius in {city}, feels like "
                f"{feels_like:.1f} degrees, with {description}."
            )
        except requests.exceptions.RequestException as exc:
            logger.error("Weather request failed: %s", exc)
            return "__OFFLINE__"
        except Exception as exc:
            logger.error("Unexpected weather error: %s", exc)
            return "Something went wrong getting the weather."

    def get_news(self, count: int = 3) -> str:
        if not Config.NEWS_API_KEY:
            return "News is not configured. Please add a NEWS_API_KEY in the .env file."
        try:
            url = "https://newsapi.org/v2/top-headlines"
            params = {"country": "in", "apiKey": Config.NEWS_API_KEY, "pageSize": count}
            response = requests.get(url, params=params, timeout=6)
            data = response.json()
            if response.status_code != 200:
                return f"I could not fetch news: {data.get('message', 'unknown error')}."
            articles = data.get("articles", [])
            if not articles:
                return "I could not find any news headlines right now."
            headlines = [a["title"] for a in articles[:count] if a.get("title")]
            return "Here are the top headlines: " + ". ".join(headlines)
        except requests.exceptions.RequestException as exc:
            logger.error("News request failed: %s", exc)
            return "__OFFLINE__"
        except Exception as exc:
            logger.error("Unexpected news error: %s", exc)
            return "Something went wrong getting the news."


# ============================================================================
# FILE COMMANDS
# ============================================================================

class FileCommands:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir
        os.makedirs(self.workspace_dir, exist_ok=True)

    def _resolve(self, name: str) -> str:
        safe_name = os.path.basename(name.strip())
        return os.path.join(self.workspace_dir, safe_name)

    def create_file(self, filename: str, content: str = "") -> str:
        try:
            path = self._resolve(filename)
            if os.path.exists(path):
                return f"A file named {filename} already exists."
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Created file {filename} in the Ayra workspace folder."
        except OSError as exc:
            logger.error("File creation failed: %s", exc)
            return f"I could not create the file {filename}."

    def delete_file(self, filename: str) -> str:
        try:
            path = self._resolve(filename)
            if not os.path.isfile(path):
                return f"I could not find a file named {filename} in the workspace."
            os.remove(path)
            return f"Deleted file {filename}."
        except OSError as exc:
            logger.error("File deletion failed: %s", exc)
            return f"I could not delete the file {filename}."

    def create_folder(self, folder_name: str) -> str:
        try:
            path = self._resolve(folder_name)
            if os.path.exists(path):
                return f"A folder named {folder_name} already exists."
            os.makedirs(path)
            return f"Created folder {folder_name} in the Ayra workspace."
        except OSError as exc:
            logger.error("Folder creation failed: %s", exc)
            return f"I could not create the folder {folder_name}."

    def delete_folder(self, folder_name: str) -> str:
        try:
            path = self._resolve(folder_name)
            if not os.path.isdir(path):
                return f"I could not find a folder named {folder_name} in the workspace."
            shutil.rmtree(path)
            return f"Deleted folder {folder_name}."
        except OSError as exc:
            logger.error("Folder deletion failed: %s", exc)
            return f"I could not delete the folder {folder_name}."


# ============================================================================
# UTILS COMMANDS (calculator, time, date)
# ============================================================================

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}


class UtilsCommands:
    def calculate(self, expression: str) -> str:
        try:
            cleaned = (
                expression.lower()
                .replace("plus", "+")
                .replace("minus", "-")
                .replace("times", "*")
                .replace("multiplied by", "*")
                .replace("divided by", "/")
                .replace("x", "*")
            )
            tree = ast.parse(cleaned, mode="eval")
            result = self._eval_node(tree.body)
            return f"The answer is {result}."
        except (SyntaxError, ValueError, ZeroDivisionError, TypeError) as exc:
            logger.warning("Calculation failed for '%s': %s", expression, exc)
            return "I could not calculate that. Please give me a simple math expression."

    def _eval_node(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Unsupported constant")
        if isinstance(node, ast.BinOp):
            op_func = _ALLOWED_OPERATORS.get(type(node.op))
            if not op_func:
                raise ValueError("Unsupported operator")
            return op_func(self._eval_node(node.left), self._eval_node(node.right))
        if isinstance(node, ast.UnaryOp):
            op_func = _ALLOWED_OPERATORS.get(type(node.op))
            if not op_func:
                raise ValueError("Unsupported operator")
            return op_func(self._eval_node(node.operand))
        raise ValueError("Unsupported expression")

    def get_time(self) -> str:
        now = datetime.now().strftime("%I:%M %p")
        return f"The current time is {now}."

    def get_date(self) -> str:
        today = datetime.now().strftime("%A, %d %B %Y")
        return f"Today is {today}."


# ============================================================================
# ASSISTANT (orchestrator: wake word, routing, offline fallback)
# ============================================================================

def has_internet(timeout: float = 2.0) -> bool:
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except OSError:
        return False


class Assistant:
    def __init__(self, on_status_change=None, on_transcript=None):
        self.language = Config.DEFAULT_LANGUAGE
        self.on_status_change = on_status_change or (lambda status: None)
        self.on_transcript = on_transcript or (lambda who, text: None)

        self.memory = Memory()
        self.voice_in = VoiceInput(language=self.language)
        self.voice_out = VoiceOutput()
        self.gpt = GPTEngine(self.memory)
        self.face = FaceUI()

        self.system_cmds = SystemCommands(SCREENSHOT_DIR, CAPTURE_DIR)
        self.web_cmds = WebCommands()
        self.file_cmds = FileCommands(WORKSPACE_DIR)
        self.util_cmds = UtilsCommands()

        self._running = False
        self._listen_thread = None

    def start(self):
        self.face.start()
        self._running = True
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()
        logger.info("Assistant started.")

    def stop(self):
        self._running = False
        self.voice_out.stop()
        self.face.stop()
        logger.info("Assistant stopped.")

    def set_language(self, language: str):
        self.language = language
        self.voice_in.set_language(language)

    def _say(self, text: str):
        self.on_transcript("Ayra", text)
        done_event = threading.Event()

        def on_word(_word):
            self.face.set_mouth(True)

        def on_done():
            self.face.set_mouth(False)
            done_event.set()

        self.voice_out.speak(text, on_word=on_word, on_done=on_done)
        done_event.wait(timeout=30)

    def _listen_loop(self):
        if not self.voice_in.is_available():
            self.on_status_change("No microphone detected. Voice input disabled.")
            logger.error("No microphone available; listening loop exiting.")
            return

        while self._running:
            self.on_status_change("Waiting for wake word 'Ayra'...")
            heard = self.voice_in.listen_once(timeout=5, phrase_time_limit=4)

            if heard == "__OFFLINE__":
                self.on_status_change(t("no_internet", self.language))
                time.sleep(2)
                continue

            if not heard:
                continue

            if any(wake in heard for wake in Config.WAKE_WORDS):
                self.on_transcript("You", heard)
                self.on_status_change(t("listening", self.language))
                self._say(t("greeting", self.language))
                self._handle_conversation_turn()

    def _handle_conversation_turn(self):
        self.on_status_change("Listening for your command...")
        command_text = self.voice_in.listen_once(timeout=6, phrase_time_limit=10)

        if command_text == "__OFFLINE__":
            self._say(t("no_internet", self.language))
            return
        if not command_text:
            self._say(t("not_understood", self.language))
            return

        self.on_transcript("You", command_text)
        response = self.process_command(command_text)
        self._say(response)

    def process_text_input(self, text: str) -> str:
        self.on_transcript("You", text)
        response = self.process_command(text)
        self._say(response)
        return response

    def process_command(self, text: str) -> str:
        text = text.lower().strip()
        self.memory.add("user", text)

        online = has_internet()

        try:
            response = self._route(text, online)
        except Exception as exc:
            logger.error("Unhandled error processing command '%s': %s", text, exc)
            response = t("error", self.language)

        if response == "__OFFLINE__":
            response = t("no_internet", self.language)

        self.memory.add("assistant", response)
        return response

    def _route(self, text: str, online: bool) -> str:
        if "time" in text and "what" in text:
            return self.util_cmds.get_time()
        if "date" in text and ("what" in text or "today" in text):
            return self.util_cmds.get_date()

        calc_match = re.search(r"calculate (.+)|what is (.+)", text)
        if calc_match and any(ch.isdigit() for ch in text):
            expr = calc_match.group(1) or calc_match.group(2)
            return self.util_cmds.calculate(expr)

        if "create a file" in text or "create file" in text:
            name = self._extract_after(text, ["create a file named", "create a file", "create file"])
            return self.file_cmds.create_file(name or "new_file.txt")
        if "delete a file" in text or "delete file" in text:
            name = self._extract_after(text, ["delete a file named", "delete a file", "delete file"])
            return self.file_cmds.delete_file(name or "")
        if "create a folder" in text or "create folder" in text:
            name = self._extract_after(text, ["create a folder named", "create a folder", "create folder"])
            return self.file_cmds.create_folder(name or "new_folder")
        if "delete a folder" in text or "delete folder" in text:
            name = self._extract_after(text, ["delete a folder named", "delete a folder", "delete folder"])
            return self.file_cmds.delete_folder(name or "")

        if "open notepad" in text:
            return self.system_cmds.open_notepad()
        if "open chrome" in text:
            return self.system_cmds.open_chrome()
        if "open vs code" in text or "open visual studio code" in text or "open vscode" in text:
            return self.system_cmds.open_vscode()

        if "shut down" in text or "shutdown" in text:
            return self.system_cmds.shutdown()
        if "restart" in text:
            return self.system_cmds.restart()
        if "sleep" in text:
            return self.system_cmds.sleep()

        volume_match = re.search(r"volume to (\d+)", text)
        if volume_match:
            return self.system_cmds.set_volume(int(volume_match.group(1)))
        if "mute" in text:
            return self.system_cmds.mute()

        if "screenshot" in text:
            return self.system_cmds.take_screenshot()
        if "camera" in text or "take a photo" in text or "take my picture" in text:
            return self.system_cmds.capture_camera_photo()

        if "battery" in text:
            return self.system_cmds.battery_status()

        if "internet speed" in text or "network speed" in text:
            if not online:
                return t("no_internet", self.language)
            return self.system_cmds.internet_speed()

        if not online:
            return t("no_internet", self.language)

        if "search google for" in text or "google search for" in text or "search for" in text:
            query = self._extract_after(text, ["search google for", "google search for", "search for"])
            return self.web_cmds.google_search(query or text)

        if "youtube" in text or "play" in text:
            query = self._extract_after(text, ["search youtube for", "play on youtube", "youtube", "play"])
            return self.web_cmds.youtube_search(query or text)

        if "whatsapp" in text:
            return (
                "To send a WhatsApp message, please use the text box in the app and type: "
                "whatsapp +countrycode phonenumber your message here."
            )
        if text.startswith("whatsapp +"):
            parts = text.split(" ", 2)
            if len(parts) >= 3:
                return self.web_cmds.send_whatsapp_message(parts[1], parts[2])
            return "Please provide a phone number and a message."

        if "wikipedia" in text:
            query = self._extract_after(text, ["search wikipedia for", "wikipedia"])
            return self.web_cmds.wikipedia_summary(query or text)

        if "weather" in text:
            city_match = re.search(r"weather in (.+)", text)
            city = city_match.group(1).strip() if city_match else None
            return self.web_cmds.get_weather(city)

        if "news" in text:
            return self.web_cmds.get_news()

        if self.gpt.is_available():
            return self.gpt.ask(text)

        return t("not_understood", self.language)

    @staticmethod
    def _extract_after(text: str, prefixes) -> str:
        for prefix in sorted(prefixes, key=len, reverse=True):
            idx = text.find(prefix)
            if idx != -1:
                return text[idx + len(prefix) :].strip()
        return ""


# ============================================================================
# GUI (CustomTkinter dark UI)
# ============================================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AyraApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Ayra Voice Assistant")
        self.geometry("820x600")
        self.minsize(700, 500)
        self.configure(fg_color="#0f1117")

        self.assistant = Assistant(
            on_status_change=self._threadsafe_status,
            on_transcript=self._threadsafe_transcript,
        )

        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self):
        header = ctk.CTkFrame(self, fg_color="#161925", corner_radius=0, height=70)
        header.pack(side="top", fill="x")

        title_label = ctk.CTkLabel(
            header,
            text=f"● {Config.ASSISTANT_NAME}",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#7dd3fc",
        )
        title_label.pack(side="left", padx=20, pady=15)

        self.language_menu = ctk.CTkOptionMenu(
            header,
            values=["English", "Hindi", "Odia"],
            command=self._on_language_change,
            width=140,
        )
        self.language_menu.pack(side="right", padx=20, pady=15)

        self.status_label = ctk.CTkLabel(
            self,
            text="Press Start to begin listening.",
            font=ctk.CTkFont(size=13),
            text_color="#94a3b8",
        )
        self.status_label.pack(side="top", fill="x", padx=20, pady=(10, 0))

        self.transcript_box = ctk.CTkTextbox(
            self,
            fg_color="#12141c",
            text_color="#e2e8f0",
            font=ctk.CTkFont(size=14),
            wrap="word",
        )
        self.transcript_box.pack(side="top", fill="both", expand=True, padx=20, pady=10)
        self.transcript_box.configure(state="disabled")

        input_frame = ctk.CTkFrame(self, fg_color="transparent")
        input_frame.pack(side="bottom", fill="x", padx=20, pady=(0, 20))

        self.text_entry = ctk.CTkEntry(
            input_frame, placeholder_text="Type a command and press Enter..."
        )
        self.text_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.text_entry.bind("<Return>", self._on_text_submit)

        self.start_button = ctk.CTkButton(
            input_frame, text="Start Listening", command=self._on_start, width=140
        )
        self.start_button.pack(side="left", padx=(0, 10))

        self.stop_button = ctk.CTkButton(
            input_frame,
            text="Stop",
            command=self._on_stop,
            width=100,
            fg_color="#7f1d1d",
            hover_color="#991b1b",
        )
        self.stop_button.pack(side="left")

    def _on_start(self):
        warnings = Config.validate()
        for warning in warnings:
            self._append_transcript("System", warning)
        self.assistant.start()
        self.status_label.configure(text="Listening for wake word 'Ayra'...")

    def _on_stop(self):
        self.assistant.stop()
        self.status_label.configure(text="Stopped.")

    def _on_language_change(self, choice: str):
        mapping = {"English": "en", "Hindi": "hi", "Odia": "od"}
        lang_code = mapping.get(choice, "en")
        self.assistant.set_language(lang_code)
        self._append_transcript("System", f"Language switched to {choice}.")

    def _on_text_submit(self, _event=None):
        text = self.text_entry.get().strip()
        if not text:
            return
        self.text_entry.delete(0, "end")
        threading.Thread(
            target=self.assistant.process_text_input, args=(text,), daemon=True
        ).start()

    def _on_close(self):
        try:
            self.assistant.stop()
        except Exception as exc:
            logger.error("Error while closing: %s", exc)
        self.destroy()

    def _threadsafe_status(self, status: str):
        self.after(0, lambda: self.status_label.configure(text=status))

    def _threadsafe_transcript(self, who: str, text: str):
        self.after(0, lambda: self._append_transcript(who, text))

    def _append_transcript(self, who: str, text: str):
        self.transcript_box.configure(state="normal")
        self.transcript_box.insert("end", f"{who}: {text}\n\n")
        self.transcript_box.see("end")
        self.transcript_box.configure(state="disabled")


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    logger.info("Starting Ayra Voice Assistant...")
    warnings = Config.validate()
    for warning in warnings:
        logger.warning(warning)

    try:
        app = AyraApp()
        app.mainloop()
    except Exception as exc:
        logger.critical("Fatal error while running Ayra: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()