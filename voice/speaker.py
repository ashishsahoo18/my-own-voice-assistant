import pyttsx3


class VoiceSpeaker:
    """Speak text with a female voice when available."""

    def __init__(self) -> None:
        self.engine = pyttsx3.init()
        self._configure_voice()

    def _configure_voice(self) -> None:
        voices = self.engine.getProperty("voices")
        for voice in voices:
            name = voice.name.lower()
            if "female" in name or "zira" in name or "sapi" in name:
                self.engine.setProperty("voice", voice.id)
                break
        self.engine.setProperty("rate", 170)

    def speak(self, text: str) -> None:
        if not text:
            return
        self.engine.say(text)
        self.engine.runAndWait()
