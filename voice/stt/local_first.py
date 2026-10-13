"""Local-first hybrid STT orchestrator with configurable offline priority and external fallback."""

from __future__ import annotations

import logging
from typing import Optional

import speech_recognition as sr

from voice.stt.base import SpeechToTextEngine, TranscriptionResult
from voice.stt.google_engine import GoogleSTTEngine
from voice.stt.vosk_engine import VoskSTTEngine


class LocalFirstSTTEngine(SpeechToTextEngine):
    """Prioritizes offline local recognition, falling back to external STT only when explicitly permitted."""

    def __init__(
        self,
        local_engine: Optional[SpeechToTextEngine] = None,
        fallback_engine: Optional[SpeechToTextEngine] = None,
        fallback_external_allowed: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.local_engine = local_engine or VoskSTTEngine(logger=self.logger)
        self.fallback_engine = fallback_engine or GoogleSTTEngine(logger=self.logger)
        self.fallback_external_allowed = fallback_external_allowed

    @property
    def name(self) -> str:
        return "local_first_hybrid"

    @property
    def is_offline(self) -> bool:
        # Defaults to True when primary local engine is available
        return self.local_engine.is_available()

    def is_available(self) -> bool:
        """Available if either the local engine or fallback engine is functional."""
        return self.local_engine.is_available() or (
            self.fallback_external_allowed and self.fallback_engine.is_available()
        )

    def transcribe(
        self,
        audio_data: sr.AudioData,
        language: str = "en",
    ) -> TranscriptionResult:
        """Attempt local offline recognition first; fallback to external service if needed and allowed."""
        # 1. Try local offline engine
        if self.local_engine.is_available():
            try:
                res = self.local_engine.transcribe(audio_data, language=language)
                if not res.is_empty:
                    return res
                self.logger.info("Local engine produced empty transcript; checking fallback...")
            except Exception as exc:
                self.logger.warning("Local STT engine failed (%s); checking fallback...", exc)

        # 2. Check if external fallback is permitted
        if not self.fallback_external_allowed:
            self.logger.info("External fallback is disabled by privacy policy; returning offline result.")
            return TranscriptionResult(
                text="",
                confidence=0.0,
                engine=self.local_engine.name,
                is_offline=True,
                external_service_disclosed=False,
            )

        # 3. Use external fallback engine with disclosure
        if self.fallback_engine.is_available():
            self.logger.info("Falling back to external STT engine: %s", self.fallback_engine.name)
            return self.fallback_engine.transcribe(audio_data, language=language)

        raise RuntimeError("No functional speech recognition engine available (local failed, fallback unavailable).")
