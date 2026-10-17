"""Framework-independent domain models used by playback and UI layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Tuple


CURRENT_SETTINGS_VERSION = 3


@dataclass(frozen=True)
class Settings:
    """Validated user preferences.

    The model deliberately has no Qt/Tk dependency, so it is safe to pass between
    a repository, the playback service, and a PySide6 UI.
    """

    schema_version: int = CURRENT_SETTINGS_VERSION
    countdown_seconds: int = 3
    window_opacity: float = 1.0
    always_on_top: bool = True
    hotkeys: Mapping[str, str] = field(default_factory=dict)
    hotkey_keys: Tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7", "8")
    song_slots: Tuple[str | None, ...] = (None,) * 8
    keyboard_layout: str = "old"
    pause_hotkey: str = "f9"
    focus_lock_enabled: bool = False
    resume_on_sky_focus: bool = True
    reduced_motion: bool = False

    def __post_init__(self) -> None:
        # Prevent callers from mutating a frozen Settings through its mapping.
        object.__setattr__(self, "hotkeys", MappingProxyType(dict(self.hotkeys)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "countdown_seconds": self.countdown_seconds,
            "window_opacity": self.window_opacity,
            "always_on_top": self.always_on_top,
            "hotkeys": dict(self.hotkeys),
            "hotkey_keys": list(self.hotkey_keys),
            "song_slots": list(self.song_slots),
            "keyboard_layout": self.keyboard_layout,
            "pause_hotkey": self.pause_hotkey,
            "focus_lock_enabled": self.focus_lock_enabled,
            "resume_on_sky_focus": self.resume_on_sky_focus,
            "reduced_motion": self.reduced_motion,
        }


@dataclass(frozen=True)
class FavoriteEntry:
    """A favorite referencing a sheet below the trusted sheet directory."""

    name: str
    path: str
    sheet_type: str = "JSON"


@dataclass(frozen=True)
class NoteEvent:
    """One sheet event; ``time`` keeps the source sheet's time unit."""

    time: float
    keys: Tuple[str, ...]

    @property
    def key(self) -> str | Tuple[str, ...]:
        """Compatibility view for code that expects the original ``key`` field."""
        return self.keys[0] if len(self.keys) == 1 else self.keys


@dataclass(frozen=True)
class SongSheet:
    """A fully validated macro sheet."""

    title: str
    notes: Tuple[NoteEvent, ...]
    source_name: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SheetCompatibility:
    """Result of checking whether a sheet can be played by one key layout."""

    source_name: str
    note_count: int = 0
    unsupported_keys: Tuple[str, ...] = ()
    error: str | None = None

    @property
    def playable(self) -> bool:
        return self.error is None and not self.unsupported_keys
