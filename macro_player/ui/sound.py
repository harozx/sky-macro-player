"""Preview tones: 15 short sine notes (C major, C4–C6) like Sky's instrument."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QUrl

SEMITONES = (0, 2, 4, 5, 7, 9, 11, 12, 14, 16, 17, 19, 21, 23, 24)
BASE_HZ = 261.63
SAMPLE_RATE = 22050


def write_tone(path: Path, frequency: float, seconds: float = .45) -> None:
    frames = int(SAMPLE_RATE * seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        data = bytearray()
        for index in range(frames):
            t = index / SAMPLE_RATE
            envelope = min(1., t * 80) * math.exp(-5.5 * t)
            sample = envelope * (math.sin(2 * math.pi * frequency * t)
                                 + .25 * math.sin(4 * math.pi * frequency * t))
            data += struct.pack("<h", int(max(-1., min(1., sample * .55)) * 32767))
        handle.writeframes(bytes(data))


def ensure_tones(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, semitone in enumerate(SEMITONES):
        path = folder / f"note{index:02d}.wav"
        if not path.exists():
            write_tone(path, BASE_HZ * 2 ** (semitone / 12))
        paths.append(path)
    return paths


class PreviewSynth(QObject):
    """Plays the tone for each lit key; silently unavailable without audio."""

    def __init__(self, folder: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.folder = folder
        self._effects = None
        self.available = True

    def _load(self) -> bool:
        if self._effects is not None:
            return True
        try:
            from PySide6.QtMultimedia import QSoundEffect
            effects = []
            for path in ensure_tones(self.folder):
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(path)))
                effect.setVolume(.6)
                effects.append(effect)
        except Exception:
            self.available = False
            return False
        self._effects = effects
        return True

    def play_indices(self, indices: list[int]) -> None:
        if not self.available or not self._load():
            return
        for index in indices:
            if 0 <= index < len(self._effects):
                self._effects[index].play()
