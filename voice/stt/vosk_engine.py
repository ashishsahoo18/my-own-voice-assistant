"""Offline local Speech-to-Text engine powered by Vosk."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import speech_recognition as sr

from voice.stt.base import SpeechToTextEngine, TranscriptionResult


class VoskSTTEngine(SpeechToTextEngine):
    """Local offline speech recognition using lightweight Kaldi/Vosk models."""

    def __init__(
        self,
        model_path: Optional[str | Path] = None,
        language: str = "en-us",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.language = language
        self.custom_model_path = Path(model_path) if model_path else None
        self.logger = logger or logging.getLogger(__name__)

        self._model = None
        self._is_initialized = False
        self._init_error: Optional[str] = None

    @property
    def name(self) -> str:
        return "vosk_local"

    @property
    def is_offline(self) -> bool:
        return True

    def _locate_model_directory(self) -> Optional[Path]:
        """Find an existing Vosk model directory."""
        if self.custom_model_path and self.custom_model_path.exists():
            return self.custom_model_path

        # Check project models/vosk directory
        project_root = Path(__file__).resolve().parent.parent.parent
        proj_model = project_root / "models" / "vosk"
        if proj_model.exists():
            return proj_model

        # Check standard user cache paths
        cache_dirs = [
            Path.home() / ".cache" / "vosk",
            Path(os.getenv("LOCALAPPDATA", "")) / "vosk",
        ]
        for cdir in cache_dirs:
            if cdir.exists():
                for entry in cdir.iterdir():
                    if entry.is_dir() and "vosk-model" in entry.name:
                        return entry

        return None

    def is_available(self) -> bool:
        """Return True if vosk is installed and an offline model is present or loadable."""
        try:
            import vosk
            model_dir = self._locate_model_directory()
            return model_dir is not None and model_dir.exists()
        except ImportError:
            return False

    def _ensure_model_loaded(self) -> None:
        """Load Vosk model into memory if not already cached."""
        if self._is_initialized:
            if self._init_error:
                raise RuntimeError(self._init_error)
            return

        try:
            import vosk
            model_dir = self._locate_model_directory()
            if model_dir is None:
                # Attempt automatic retrieval if internet is accessible
                try:
                    self.logger.info("Attempting to load Vosk model for %s", self.language)
                    self._model = vosk.Model(lang=self.language)
                except Exception as exc:
                    self._init_error = f"No offline Vosk model found and auto-load failed: {exc}"
                    self._is_initialized = True
                    raise RuntimeError(self._init_error) from exc
            else:
                self.logger.info("Loading offline Vosk model from: %s", model_dir)
                self._model = vosk.Model(str(model_dir))

            self._is_initialized = True
        except Exception as exc:
            self._init_error = str(exc)
            self._is_initialized = True
            raise RuntimeError(f"Failed to initialize Vosk model: {exc}") from exc

    def transcribe(
        self,
        audio_data: sr.AudioData,
        language: str = "en",
    ) -> TranscriptionResult:
        """Transcribe audio completely offline using Vosk."""
        start_time = time.perf_counter()

        try:
            self._ensure_model_loaded()
            import vosk

            sample_rate = 16000
            raw_pcm = audio_data.get_raw_data(convert_rate=sample_rate, convert_width=2)

            rec = vosk.KaldiRecognizer(self._model, sample_rate)
            rec.SetWords(True)
            rec.AcceptWaveform(raw_pcm)

            final_json = rec.FinalResult()
            result_data = json.loads(final_json)
            text = (result_data.get("text") or "").strip()

            latency = time.perf_counter() - start_time
            self.logger.info("Vosk offline transcription completed in %.3fs: '%s'", latency, text)

            return TranscriptionResult(
                text=text,
                confidence=1.0 if text else 0.0,
                engine=self.name,
                is_offline=True,
                latency_s=latency,
                external_service_disclosed=False,
                details=result_data,
            )
        except Exception as exc:
            latency = time.perf_counter() - start_time
            self.logger.error("Vosk transcription failed: %s", exc)
            raise RuntimeError(f"Vosk transcription error: {exc}") from exc
