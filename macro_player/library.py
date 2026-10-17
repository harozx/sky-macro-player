"""Song library: discovery, metadata, compatibility, layer policies and import."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .domain import FavoriteEntry, SongSheet
from .i18n import N_, tr
from .repositories import (
    FavoritesRepository,
    RepositoryError,
    SheetRepository,
    _read_json,
)

_LAYERED_KEY = re.compile(r"^(\d+)Key(\d+)$")
MAX_IMPORT_BYTES = 5 * 1024 * 1024
LAYER_POLICY_LABELS = {
    None: N_("Chặn (mặc định)"),
    "merge": N_("Gộp mọi lớp về 15 phím"),
    "layer1": N_("Chỉ phát lớp 1"),
}


@dataclass(frozen=True, slots=True)
class Song:
    path: Path
    title: str
    favorite: bool = False
    playable: bool = True
    duration_ms: int = 0
    note_count: int = 0
    added_at: float = 0.0
    relative: str = ""
    layered: bool = False
    play_count: int = 0
    last_played: float = 0.0

    @property
    def identity(self) -> str:
        return self.relative or self.path.as_posix()

    @property
    def density(self) -> float:
        """Notes per second, a rough difficulty hint."""
        seconds = self.duration_ms / 1000
        return self.note_count / seconds if seconds > 0 else 0.0

    @property
    def difficulty(self) -> str:
        if not self.note_count:
            return ""
        if self.density < 3:
            return tr("Dễ")
        if self.density < 6:
            return tr("Vừa")
        return tr("Khó")


def is_layered(sheet: SongSheet) -> bool:
    for note in sheet.notes:
        for key in note.keys:
            match = _LAYERED_KEY.match(key)
            if match and match.group(1) != "1":
                return True
    return False


def apply_layer_policy(sheet: SongSheet, policy: str | None) -> list[tuple[float, tuple[str, ...]]]:
    """Return playable events; layers are changed only by an explicit policy."""
    events: list[tuple[float, tuple[str, ...]]] = []
    for note in sheet.notes:
        keys: list[str] = []
        for key in note.keys:
            match = _LAYERED_KEY.match(key)
            if match and match.group(1) != "1" and policy is not None:
                if policy == "layer1":
                    continue
                key = f"1Key{match.group(2)}"  # policy == "merge"
            if key not in keys:
                keys.append(key)
        if keys:
            events.append((note.time, tuple(keys)))
    return events


def unsupported_keys(events: Iterable[tuple[float, Sequence[str]]],
                     supported: Iterable[str]) -> tuple[str, ...]:
    allowed = set(supported)
    return tuple(sorted(
        {key for _, keys in events for key in keys if key not in allowed},
        key=str.casefold,
    ))


@dataclass(frozen=True, slots=True)
class ImportCandidate:
    source: Path
    target_name: str
    title: str = ""
    note_count: int = 0
    duration_ms: int = 0
    error: str | None = None
    layered: bool = False
    conflict: bool = False

    @property
    def valid(self) -> bool:
        return self.error is None


def path_fingerprint(path: Path) -> tuple[int, int]:
    stat = Path(path).stat()
    return stat.st_mtime_ns, stat.st_size


@dataclass(frozen=True, slots=True)
class ImportRecord:
    """An imported file and the bytes it replaced (None when it was new)."""

    path: Path
    previous: bytes | None
    fingerprint: tuple[int, int]


class Library:
    """Reads sheets below one trusted root and caches parsed sheets by file state."""

    def __init__(self, root: Path, favorites_path: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.sheets = SheetRepository(self.root)
        self.favorites_repository = FavoritesRepository(favorites_path, self.root)
        self.favorites_error: str | None = None
        self._cache: dict[str, tuple[tuple[int, int], SongSheet | None, str | None]] = {}

    # -- reading ---------------------------------------------------------
    def relative_id(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self.sheets.root).as_posix()

    def _fingerprint(self, path: Path) -> tuple[int, int]:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def load(self, relative: str) -> SongSheet:
        """Parse a sheet, re-reading it whenever the file changed on disk."""
        path = self.sheets.root / relative
        try:
            fingerprint = self._fingerprint(path)
        except OSError as exc:
            self._cache.pop(relative.casefold(), None)
            raise RepositoryError(tr("Không tìm thấy sheet '{relative}'.").format(
                relative=relative)) from exc
        cached = self._cache.get(relative.casefold())
        if cached is not None and cached[0] == fingerprint:
            if cached[1] is None:
                raise RepositoryError(cached[2] or tr("Sheet không hợp lệ."))
            return cached[1]
        try:
            sheet = self.sheets.load(relative)
        except RepositoryError as exc:
            self._cache[relative.casefold()] = (fingerprint, None, str(exc))
            raise
        self._cache[relative.casefold()] = (fingerprint, sheet, None)
        return sheet

    def load_favorites(self) -> set[str]:
        try:
            entries = self.favorites_repository.load()
        except RepositoryError as exc:
            self.favorites_error = str(exc)
            return set()
        self.favorites_error = None
        return {entry.path.casefold() for entry in entries}

    def save_favorites(self, relatives: Iterable[str]) -> None:
        entries = [FavoriteEntry(Path(path).name, path) for path in relatives]
        if self.favorites_error:
            self.favorites_repository.recover(entries)
            self.favorites_error = None
        else:
            self.favorites_repository.save(entries)

    def scan(self, supported_keys: Iterable[str],
             policies: Mapping[str, str | None] | None = None,
             counts: Mapping[str, int] | None = None,
             last_played: Mapping[str, float] | None = None) -> list[Song]:
        supported = tuple(supported_keys)
        policies = policies or {}
        counts = counts or {}
        last_played = last_played or {}
        favorites = self.load_favorites()
        songs = []
        for relative in self.sheets.list():
            path = self.sheets.root / relative
            try:
                sheet = self.load(relative)
            except RepositoryError:
                sheet = None
            try:
                added_at = path.stat().st_mtime
            except OSError:
                added_at = 0.0
            if sheet is None:
                songs.append(Song(path, Path(relative).stem, relative.casefold() in favorites,
                                  playable=False, added_at=added_at, relative=relative))
                continue
            events = apply_layer_policy(sheet, policies.get(relative))
            songs.append(Song(
                path, sheet.title, relative.casefold() in favorites,
                playable=bool(events) and not unsupported_keys(events, supported),
                duration_ms=int(sheet.notes[-1].time) if sheet.notes else 0,
                note_count=len(sheet.notes),
                added_at=added_at,
                relative=relative,
                layered=is_layered(sheet),
                play_count=counts.get(relative, 0),
                last_played=last_played.get(relative, 0.0),
            ))
        return songs

    def prepare(self, relative: str, supported_keys: Iterable[str], policy: str | None):
        """Validate right before playback; return ``(events, moments, duration)``."""
        sheet = self.load(relative)
        events = apply_layer_policy(sheet, policy)
        missing = unsupported_keys(events, supported_keys)
        if missing:
            hint = (tr(" Chọn cách xử lý lớp 2Key/3Key trong chi tiết bài.")
                    if is_layered(sheet) and policy is None else "")
            raise RepositoryError(tr("Sheet dùng phím chưa hỗ trợ: {0}.{hint}").format(
                ', '.join(missing), hint=hint))
        if not events:
            raise RepositoryError(tr("Sheet không có nốt nào để phát."))
        moments = sorted({int(time) for time, _ in events})
        return events, moments, moments[-1] if moments else 0

    # -- import ----------------------------------------------------------
    def inspect_import(self, source: Path) -> ImportCandidate:
        source = Path(source)
        name = source.name
        conflict = (self.root / name).exists()
        if source.suffix.lower() not in {".txt", ".json"}:
            return ImportCandidate(source, name, error=tr("Chỉ nhận file .txt hoặc .json."),
                                   conflict=conflict)
        try:
            if source.stat().st_size > MAX_IMPORT_BYTES:
                return ImportCandidate(source, name, error=tr("File lớn hơn 5 MB."),
                                       conflict=conflict)
            sheet = SheetRepository._parse(_read_json(source), source_name=name)
        except (OSError, RepositoryError) as exc:
            return ImportCandidate(source, name, error=str(exc), conflict=conflict)
        if not sheet.notes:
            return ImportCandidate(source, name, sheet.title, error=tr("Sheet không có nốt nào."),
                                   conflict=conflict)
        return ImportCandidate(
            source, name, sheet.title, len(sheet.notes), int(sheet.notes[-1].time),
            layered=is_layered(sheet), conflict=conflict,
        )

    def free_name(self, name: str) -> str:
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate, index = name, 2
        while (self.root / candidate).exists():
            candidate = f"{stem} ({index}){suffix}"
            index += 1
        return candidate

    def import_file(self, candidate: ImportCandidate, action: str = "rename") -> Path | None:
        """Copy a validated sheet into the library; the source is never changed."""
        record = self.import_with_undo(candidate, action)
        return record.path if record is not None else None

    def import_with_undo(self, candidate: ImportCandidate,
                         action: str = "rename") -> ImportRecord | None:
        """Like ``import_file`` but remember what is needed to undo the copy."""
        if not candidate.valid or action == "skip":
            return None
        name = candidate.target_name
        if (self.root / name).exists():
            if action == "rename":
                name = self.free_name(name)
            elif action != "overwrite":
                raise ValueError(f"Unknown import action: {action}")
        destination = self.root / name
        try:
            if destination.exists() and destination.resolve() == candidate.source.resolve():
                return None
            previous = destination.read_bytes() if destination.exists() else None
            shutil.copy2(candidate.source, destination)
            return ImportRecord(destination, previous, self._fingerprint(destination))
        except OSError as exc:
            raise RepositoryError(tr("Không thể chép '{name}': {exc}").format(
                name=candidate.source.name, exc=exc)) from exc

    def undo_import(self, records: Iterable[ImportRecord]) -> tuple[int, int]:
        """Remove imported copies or restore what they overwrote.

        A file changed after the import is left alone. Returns (undone, kept).
        """
        undone = kept = 0
        for record in records:
            try:
                if self._fingerprint(record.path) != record.fingerprint:
                    kept += 1
                    continue
                if record.previous is None:
                    record.path.unlink()
                else:
                    record.path.write_bytes(record.previous)
            except OSError:
                kept += 1
                continue
            self._cache.pop(self.relative_id(record.path).casefold(), None)
            undone += 1
        return undone, kept
