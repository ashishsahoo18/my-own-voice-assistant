"""External fallback Speech-to-Text engine using Google Speech Recognition API with explicit privacy disclosure."""

from __future__ import annotations

import logging
import time
from typing import Optional

import speech_recognition as sr

from core.logging import get_audit_logger
from voice.stt.base import SpeechToTextEngine, TranscriptionResult


class GoogleSTTEngine(SpeechToTextEngine):
    """External Google Speech Recognition fallback engine with strict disclosure."""

    def __init__(
        self,
        recognizer: Optional[sr.Recognizer] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.recognizer = recognizer or sr.Recognizer()
        self.logger = logger or logging.getLogger(__name__)

    @property
    def name(self) -> str:
        return "google_speech_api"

    @property
    def is_offline(self) -> bool:
        return False

    def is_available(self) -> bool:
        return True

    def transcribe(
        self,
        audio_data: sr.AudioData,
        language: str = "en-US",
    ) -> TranscriptionResult:
        """Transcribe speech audio using external Google service, explicitly disclosing transmission."""
        start_time = time.perf_counter()

        # Explicit privacy disclosure
        self.logger.warning(
            "[PRIVACY DISCLOSURE] Transmitting audio data to external third-party service: Google Speech Recognition (language=%s)",
            language,
        )

        try:
            audit = get_audit_logger()
            audit.record_event(
                event_type="AUDIO_EXTERNAL_TRANSMISSION",
                action="voice.transcribe_external",
                risk_level=1,
                status="DISCLOSED",
                details={"service": "Google Speech Recognition", "language": language},
            )
        except Exception:
            pass

        try:
            text = self.recognizer.recognize_google(audio_data, language=language)
            clean_text = text.strip() if text else ""
            latency = time.perf_counter() - start_time

            self.logger.info("Google STT transcription completed in %.3fs: '%s'", latency, clean_text)
            return TranscriptionResult(
                text=clean_text,
                confidence=0.9 if clean_text else 0.0,
                engine=self.name,
                is_offline=False,
                latency_s=latency,
                external_service_disclosed=True,
                details={"external_provider": "google"},
            )
        except sr.UnknownValueError:
            latency = time.perf_counter() - start_time
            self.logger.info("Google STT: Speech was not recognized (silence or unintelligible)")
            return TranscriptionResult(
                text="",
                confidence=0.0,
                engine=self.name,
                is_offline=False,
                latency_s=latency,
                external_service_disclosed=True,
            )
        except sr.RequestError as exc:
            latency = time.perf_counter() - start_time
            self.logger.error("Google STT request failed or service unreachable: %s", exc)
            raise RuntimeError(f"Google speech recognition unavailable: {exc}") from exc
