"""Voice Activity Detection (VAD) module for OLIVER 2.0."""

from __future__ import annotations

import audioop
import math
from typing import Optional


class VoiceActivityDetector:
    """Energy-based voice activity detector with adaptive noise floor estimation."""

    def __init__(
        self,
        energy_threshold: float = 300.0,
        sample_width: int = 2,
        ratio: float = 1.5,
        smoothing: float = 0.95,
    ) -> None:
        self.energy_threshold = energy_threshold
        self.sample_width = sample_width
        self.ratio = ratio
        self.smoothing = smoothing
        self.background_energy = energy_threshold

    def calculate_energy(self, pcm_data: bytes) -> float:
        """Compute root-mean-square (RMS) energy of PCM audio frame."""
        if not pcm_data:
            return 0.0
        try:
            return float(audioop.rms(pcm_data, self.sample_width))
        except Exception:
            return 0.0

    def is_speech(self, pcm_data: bytes, custom_threshold: Optional[float] = None) -> bool:
        """Return True if audio chunk contains speech energy above background threshold."""
        energy = self.calculate_energy(pcm_data)
        thresh = custom_threshold if custom_threshold is not None else max(self.energy_threshold, self.background_energy * self.ratio)

        if energy > thresh:
            return True

        # Slowly adapt background noise floor downward or upward on non-speech frames
        self.background_energy = (self.background_energy * self.smoothing) + (energy * (1.0 - self.smoothing))
        return False

    def calibrate(self, ambient_pcm_samples: list[bytes]) -> float:
        """Calibrate baseline noise floor using ambient sample frames."""
        if not ambient_pcm_samples:
            return self.energy_threshold

        energies = [self.calculate_energy(chunk) for chunk in ambient_pcm_samples if chunk]
        if energies:
            avg_ambient = sum(energies) / len(energies)
            self.background_energy = max(50.0, avg_ambient)
            self.energy_threshold = self.background_energy * self.ratio

        return self.energy_threshold
