"""Framework-independent domain models used by playback and UI layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Tuple

CURRENT_SETTINGS_VERSION = 4


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
    custom_layout_keys: Tuple[str, ...] = ()
    speed: float = 1.0
    minimize_to_tray: bool = False
    preview_sound: bool = True
    focus_target_exe: str | None = None
    mini_position: Tuple[int, int] | None = None
    first_run_completed: bool = False
    check_updates: bool = False
    language: str = "vi"
    queue_gap_seconds: int = 1

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
            "custom_layout_keys": list(self.custom_layout_keys),
            "speed": self.speed,
            "minimize_to_tray": self.minimize_to_tray,
            "preview_sound": self.preview_sound,
            "focus_target_exe": self.focus_target_exe,
            "mini_position": list(self.mini_position) if self.mini_position else None,
            "first_run_completed": self.first_run_completed,
            "check_updates": self.check_updates,
            "language": self.language,
            "queue_gap_seconds": self.queue_gap_seconds,
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


LAYER_POLICIES = ("merge", "layer1")


@dataclass(frozen=True)
class SongPreference:
    """Per-song choices remembered between sessions."""

    speed: float | None = None
    layer_policy: str | None = None


@dataclass(frozen=True)
class HistoryEntry:
    path: str
    played_at: float


@dataclass(frozen=True)
class LibraryState:
    """Listening history, play counts, playlists and per-song preferences."""

    history: Tuple[HistoryEntry, ...] = ()
    play_counts: Mapping[str, int] = field(default_factory=dict)
    preferences: Mapping[str, SongPreference] = field(default_factory=dict)
    playlists: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("play_counts", "preferences", "playlists"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
