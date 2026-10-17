"""Typed domain and persistence layer for the macro player."""

__version__ = "2.0.0"

from .domain import FavoriteEntry, NoteEvent, Settings, SheetCompatibility, SongSheet
from .repositories import (
    FavoritesRepository,
    JsonDataError,
    RepositoryError,
    SettingsRepository,
    SheetRepository,
    UnsafePathError,
    ValidationError,
)
from .window_focus import (
    FocusService,
    WindowInfo,
    WindowsFocusService,
    choose_sky_window,
    is_sky_game_title,
    same_window_identity,
)

__all__ = [
    "__version__",
    "FavoritesRepository",
    "FavoriteEntry",
    "JsonDataError",
    "NoteEvent",
    "RepositoryError",
    "Settings",
    "SheetCompatibility",
    "SettingsRepository",
    "SheetRepository",
    "SongSheet",
    "UnsafePathError",
    "ValidationError",
    "FocusService",
    "WindowInfo",
    "WindowsFocusService",
    "choose_sky_window",
    "is_sky_game_title",
    "same_window_identity",
]
