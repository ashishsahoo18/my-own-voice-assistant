import threading
from typing import Optional

import pyttsx3


class VoiceSpeaker:
    """Speak text with configurable voice, speed, and volume."""

    def __init__(self, voice: Optional[str] = None, rate: int = 170, volume: float = 1.0) -> None:
        self.engine = pyttsx3.init()
        self.voice_id = voice
        self.rate = rate
        self.volume = max(0.0, min(1.0, volume))
        self._stopped = threading.Event()
        self._configure_voice()

    def _configure_voice(self) -> None:
        voices = self.engine.getProperty("voices")
        preferred = self.voice_id
        if preferred:
            for voice in voices:
                if voice.id == preferred:
                    self.engine.setProperty("voice", voice.id)
                    break
        else:
            for voice in voices:
                name = voice.name.lower()
                if "female" in name or "zira" in name or "sapi" in name:
                    self.engine.setProperty("voice", voice.id)
                    break
        self.engine.setProperty("rate", self.rate)
        self.engine.setProperty("volume", self.volume)

    def set_voice(self, voice_id: str) -> None:
        self.voice_id = voice_id
        self._configure_voice()

    def get_available_voices(self) -> list[dict[str, str]]:
        voices = []
        for voice in self.engine.getProperty("voices"):
            voices.append({"id": voice.id, "name": voice.name})
        return voices

    def set_rate(self, rate: int) -> None:
        self.rate = max(80, min(300, rate))
        self.engine.setProperty("rate", self.rate)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        self.engine.setProperty("volume", self.volume)

    def speak(self, text: str) -> None:
        if not text:
            return
        self._stopped.clear()
        self.engine.say(text)
        self.engine.runAndWait()

    def stop(self) -> None:
        self._stopped.set()
        self.engine.stop()
