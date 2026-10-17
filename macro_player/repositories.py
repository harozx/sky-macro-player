"""Safe JSON repositories for settings, favorites, and song sheets."""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .domain import (
    CURRENT_SETTINGS_VERSION, FavoriteEntry, NoteEvent, Settings,
    SheetCompatibility, SongSheet,
)


class RepositoryError(Exception):
    """Base class for errors suitable for presentation by the UI."""


class JsonDataError(RepositoryError):
    """A JSON file could not be read or decoded."""


class ValidationError(RepositoryError):
    """A decoded value does not satisfy the application's schema."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        self.field = field
        super().__init__(f"{field}: {message}" if field else message)


class UnsafePathError(RepositoryError):
    """A requested path escapes the configured sheet directory."""


def _read_json(path: Path) -> Any:
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise JsonDataError(f"Could not read '{path}': {exc}") from exc

    encodings = ("utf-16", "utf-8-sig") if payload.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "utf-16")
    decode_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            text = payload.decode(encoding)
        except UnicodeDecodeError as exc:
            decode_error = exc
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise JsonDataError(
                f"Invalid JSON in '{path.name}' at line {exc.lineno}, column {exc.colno}."
            ) from exc
    raise JsonDataError(f"'{path.name}' is not valid UTF-8 or UTF-16 text.") from decode_error


def _atomic_write_json(path: Path, value: Any) -> None:
    """Write JSON without exposing a partially written destination file."""
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except (OSError, TypeError, ValueError) as exc:
        raise RepositoryError(f"Could not save '{path}': {exc}") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _backup_invalid_file(path: Path) -> Path | None:
    """Preserve invalid user data before an explicit recovery write."""
    if not path.exists():
        return None
    index = 0
    while True:
        suffix = ".invalid.bak" if index == 0 else f".invalid.{index}.bak"
        backup = path.with_name(path.name + suffix)
        if not backup.exists():
            break
        index += 1
    try:
        shutil.copy2(path, backup)
    except OSError as exc:
        raise RepositoryError(f"Could not back up invalid '{path}': {exc}") from exc
    return backup


def _strict_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("must be an integer", field=field)
    if not minimum <= value <= maximum:
        raise ValidationError(f"must be between {minimum} and {maximum}", field=field)
    return value


def _strict_float(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("must be a number", field=field)
    converted = float(value)
    if not math.isfinite(converted) or not minimum <= converted <= maximum:
        raise ValidationError(f"must be between {minimum:g} and {maximum:g}", field=field)
    return converted


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError("must be true or false", field=field)
    return value


class SettingsRepository:
    """Loads validated settings and migrates known legacy field names."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        raw = _read_json(self.path)
        return self._parse(raw)

    def save(self, settings: Settings) -> None:
        # Parsing our serialized form also protects callers that bypass typing.
        validated = self._parse(settings.to_dict())
        _atomic_write_json(self.path, validated.to_dict())

    def recover(self, settings: Settings) -> Path | None:
        """Back up unreadable settings, then write an explicitly chosen state."""
        backup = _backup_invalid_file(self.path)
        self.save(settings)
        return backup

    @staticmethod
    def _parse(raw: Any) -> Settings:
        if not isinstance(raw, Mapping):
            raise ValidationError("settings root must be a JSON object")

        version = raw.get("schema_version", raw.get("version", CURRENT_SETTINGS_VERSION))
        version = _strict_int(version, "schema_version", minimum=0, maximum=CURRENT_SETTINGS_VERSION)

        countdown = raw.get("countdown_seconds", raw.get("countdown", 3))
        opacity = raw.get("window_opacity", raw.get("opacity", raw.get("alpha", 1.0)))
        topmost = raw.get("always_on_top", raw.get("topmost", True))
        hotkeys = raw.get("hotkeys", raw.get("shortcuts", {}))
        defaults = Settings()
        hotkey_keys = raw.get("hotkey_keys", raw.get("keys", list(defaults.hotkey_keys)))
        song_slots = raw.get("song_slots", raw.get("songs", list(defaults.song_slots)))
        keyboard_layout = raw.get("keyboard_layout", raw.get("layout", "old"))
        pause_hotkey = raw.get("pause_hotkey", "f9")
        focus_lock_enabled = raw.get("focus_lock_enabled", False)
        resume_on_sky_focus = raw.get("resume_on_sky_focus", True)
        reduced_motion = raw.get("reduced_motion", False)

        if not isinstance(hotkeys, Mapping):
            raise ValidationError("must be a JSON object", field="hotkeys")
        checked_hotkeys: dict[str, str] = {}
        for action, shortcut in hotkeys.items():
            if not isinstance(action, str) or not action.strip():
                raise ValidationError("action names must be non-empty strings", field="hotkeys")
            if not isinstance(shortcut, str) or not shortcut.strip():
                raise ValidationError(
                    f"shortcut for '{action}' must be a non-empty string", field="hotkeys"
                )
            checked_hotkeys[action.strip()] = shortcut.strip()

        if not isinstance(hotkey_keys, list) or not hotkey_keys:
            raise ValidationError("must be a non-empty list", field="hotkey_keys")
        checked_keys: list[str] = []
        for index, key in enumerate(hotkey_keys):
            if not isinstance(key, str) or not key.strip():
                raise ValidationError("must be a non-empty string", field=f"hotkey_keys[{index}]")
            checked_keys.append(key.strip())
        if len(set(key.casefold() for key in checked_keys)) != len(checked_keys):
            raise ValidationError("must not contain duplicate shortcuts", field="hotkey_keys")

        if not isinstance(song_slots, list):
            raise ValidationError("must be a list", field="song_slots")
        checked_slots: list[str | None] = []
        for index, song in enumerate(song_slots):
            if song is not None and (not isinstance(song, str) or not song.strip()):
                raise ValidationError("must be null or a non-empty string", field=f"song_slots[{index}]")
            checked_slots.append(song.strip() if isinstance(song, str) else None)
        if len(checked_slots) != len(checked_keys):
            raise ValidationError("must have the same length as hotkey_keys", field="song_slots")
        if keyboard_layout not in {"old", "new"}:
            raise ValidationError("must be 'old' or 'new'", field="keyboard_layout")
        if not isinstance(pause_hotkey, str) or not pause_hotkey.strip():
            raise ValidationError("must be a non-empty string", field="pause_hotkey")

        return Settings(
            schema_version=CURRENT_SETTINGS_VERSION,
            countdown_seconds=_strict_int(countdown, "countdown_seconds", minimum=0, maximum=30),
            window_opacity=_strict_float(opacity, "window_opacity", minimum=0.2, maximum=1.0),
            always_on_top=_strict_bool(topmost, "always_on_top"),
            hotkeys=checked_hotkeys,
            hotkey_keys=tuple(checked_keys),
            song_slots=tuple(checked_slots),
            keyboard_layout=keyboard_layout,
            pause_hotkey=pause_hotkey.strip(),
            focus_lock_enabled=_strict_bool(focus_lock_enabled, "focus_lock_enabled"),
            resume_on_sky_focus=_strict_bool(resume_on_sky_focus, "resume_on_sky_focus"),
            reduced_motion=_strict_bool(reduced_motion, "reduced_motion"),
        )


class _SheetPathPolicy:
    def __init__(self, sheets_dir: str | Path) -> None:
        self.root = Path(sheets_dir).resolve()

    def resolve(self, path: str | Path) -> Path:
        requested = Path(path)
        candidate = requested.resolve() if requested.is_absolute() else (self.root / requested).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise UnsafePathError(f"Sheet path '{path}' is outside '{self.root}'.") from exc
        if candidate.suffix.lower() not in {".json", ".txt"}:
            raise ValidationError("sheet file must use the .json or .txt extension", field="path")
        return candidate

    def relative(self, path: str | Path) -> str:
        requested = Path(path)
        if not requested.is_absolute() and requested.parts:
            # Legacy favorites are relative to the application directory and
            # therefore begin with the name of the sheet directory.
            if requested.parts[0].casefold() == self.root.name.casefold():
                requested = Path(*requested.parts[1:])
        return self.resolve(requested).relative_to(self.root).as_posix()


class FavoritesRepository:
    """Stores normalized sheet-relative paths and rejects directory traversal."""

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path, sheets_dir: str | Path) -> None:
        self.path = Path(path)
        self._paths = _SheetPathPolicy(sheets_dir)

    def load(self) -> tuple[FavoriteEntry, ...]:
        if not self.path.exists():
            return ()
        raw = _read_json(self.path)
        if isinstance(raw, list):  # Legacy representation.
            entries = raw
        elif isinstance(raw, Mapping):
            entries = raw.get("favorites", [])
        else:
            raise ValidationError("favorites root must be a list or JSON object")
        if not isinstance(entries, list):
            raise ValidationError("must be a list", field="favorites")

        normalized: list[FavoriteEntry] = []
        seen: set[str] = set()
        for index, entry in enumerate(entries):
            if isinstance(entry, str):
                source_path = entry
                name = Path(entry).name
                sheet_type = "JSON"
            elif isinstance(entry, Mapping):
                source_path = entry.get("path")
                name = entry.get("name")
                sheet_type = entry.get("type", "JSON")
                if not isinstance(name, str) or not name.strip():
                    raise ValidationError("must be a non-empty string", field=f"favorites[{index}].name")
                if not isinstance(sheet_type, str) or not sheet_type.strip():
                    raise ValidationError("must be a non-empty string", field=f"favorites[{index}].type")
            else:
                raise ValidationError("must be a path string or JSON object", field=f"favorites[{index}]")
            if not isinstance(source_path, str) or not source_path.strip():
                raise ValidationError("must be a non-empty path string", field=f"favorites[{index}].path")
            relative = self._paths.relative(source_path.strip())
            key = relative.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(FavoriteEntry(name=name.strip(), path=relative, sheet_type=sheet_type.strip()))
        return tuple(normalized)

    def save(self, favorites: Iterable[FavoriteEntry | str | Path]) -> None:
        normalized: list[FavoriteEntry] = []
        seen: set[str] = set()
        for entry in favorites:
            if isinstance(entry, FavoriteEntry):
                relative = self._paths.relative(entry.path)
                favorite = FavoriteEntry(entry.name.strip(), relative, entry.sheet_type.strip())
                if not favorite.name or not favorite.sheet_type:
                    raise ValidationError("favorite name and type must not be empty", field="favorites")
            else:
                relative = self._paths.relative(entry)
                favorite = FavoriteEntry(Path(relative).name, relative)
            key = relative.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(favorite)
        _atomic_write_json(
            self.path,
            {
                "schema_version": self.SCHEMA_VERSION,
                "favorites": [
                    {"name": item.name, "type": item.sheet_type, "path": item.path}
                    for item in normalized
                ],
            },
        )

    def recover(self, favorites: Iterable[FavoriteEntry | str | Path]) -> Path | None:
        """Back up unreadable favorites before replacing them."""
        backup = _backup_invalid_file(self.path)
        self.save(favorites)
        return backup


class SheetRepository:
    """Discovers and validates sheet files below one trusted directory."""

    def __init__(self, sheets_dir: str | Path) -> None:
        self._paths = _SheetPathPolicy(sheets_dir)

    @property
    def root(self) -> Path:
        return self._paths.root

    def list(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            path.relative_to(self.root).as_posix()
            for path in sorted(self.root.rglob("*"), key=lambda item: str(item).casefold())
            if path.is_file() and path.suffix.lower() in {".json", ".txt"}
        )

    def load(self, path: str | Path) -> SongSheet:
        resolved = self._paths.resolve(path)
        try:
            raw = _read_json(resolved)
        except FileNotFoundError as exc:
            raise JsonDataError(f"Sheet '{path}' does not exist.") from exc
        return self._parse(raw, source_name=resolved.relative_to(self.root).as_posix())

    def audit(self, path: str | Path, supported_keys: Iterable[str]) -> SheetCompatibility:
        """Validate structure and report keys unavailable in a playback layout."""
        source_name = self._paths.relative(path)
        try:
            sheet = self.load(source_name)
        except RepositoryError as exc:
            return SheetCompatibility(source_name=source_name, error=str(exc))
        supported = set(supported_keys)
        unsupported = sorted(
            {key for note in sheet.notes for key in note.keys if key not in supported},
            key=str.casefold,
        )
        return SheetCompatibility(
            source_name=source_name,
            note_count=len(sheet.notes),
            unsupported_keys=tuple(unsupported),
        )

    @staticmethod
    def _parse(raw: Any, *, source_name: str) -> SongSheet:
        if isinstance(raw, list):
            if len(raw) != 1 or not isinstance(raw[0], Mapping):
                raise ValidationError("sheet root list must contain exactly one JSON object")
            raw = raw[0]
        if not isinstance(raw, Mapping):
            raise ValidationError("sheet root must be a JSON object or a one-item list")
        notes = raw.get("songNotes")
        if not isinstance(notes, list):
            raise ValidationError("must be a list", field="songNotes")
        title_value = raw.get("name", raw.get("title", Path(source_name).stem))
        if not isinstance(title_value, str) or not title_value.strip():
            raise ValidationError("must be a non-empty string", field="name")

        parsed_notes: list[NoteEvent] = []
        previous_time = -math.inf
        for index, item in enumerate(notes):
            prefix = f"songNotes[{index}]"
            if not isinstance(item, Mapping):
                raise ValidationError("must be a JSON object", field=prefix)
            timestamp = item.get("time")
            if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
                raise ValidationError("must be a number", field=f"{prefix}.time")
            event_time = float(timestamp)
            if not math.isfinite(event_time) or event_time < 0:
                raise ValidationError("must be a finite non-negative number", field=f"{prefix}.time")
            if event_time < previous_time:
                raise ValidationError("must not be earlier than the preceding note", field=f"{prefix}.time")
            previous_time = event_time

            key_value = item.get("key")
            if isinstance(key_value, str):
                keys: Sequence[Any] = (key_value,)
            elif isinstance(key_value, list):
                keys = key_value
            else:
                raise ValidationError("must be a string or list of strings", field=f"{prefix}.key")
            if not keys:
                raise ValidationError("must contain at least one key", field=f"{prefix}.key")
            checked_keys: list[str] = []
            for key_index, key in enumerate(keys):
                if not isinstance(key, str) or not key.strip():
                    raise ValidationError(
                        "must be a non-empty string", field=f"{prefix}.key[{key_index}]"
                    )
                checked_keys.append(key.strip())
            parsed_notes.append(NoteEvent(time=event_time, keys=tuple(checked_keys)))

        metadata = {key: value for key, value in raw.items() if key not in {"songNotes", "name", "title"}}
        return SongSheet(
            title=title_value.strip(),
            notes=tuple(parsed_notes),
            source_name=source_name,
            metadata=metadata,
        )
