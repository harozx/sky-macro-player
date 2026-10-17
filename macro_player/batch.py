"""Batch processing of downloaded sheet folders.

Each file is checked and, only when it is safe, cleaned up: 2Key/3Key layers
are merged and slightly uneven timing (hand-played jitter around a clear grid)
is snapped. Anything uncertain is left untouched and flagged for listening.
Originals are never modified; results are written as new library files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .i18n import tr
from .repositories import RepositoryError, SheetRepository, _read_json
from .sheet_tools import (
    Event,
    GridInfo,
    detect_grid,
    grid_candidates,
    grid_ratio,
    has_layers,
    merge_layers,
    normalize,
    quantize,
)

SHEET_SUFFIXES = {".txt", ".json"}
EXACT_TOLERANCE_MS = 3
JITTER_TOLERANCE_MS = 15
MIN_JITTER_STEP_MS = 100
MAX_FILE_BYTES = 5 * 1024 * 1024


@dataclass
class BatchItem:
    source: Path
    title: str = ""
    status: str = "ok"  # ok | changed | review | error
    notes: list[str] = field(default_factory=list)
    events: list[Event] | None = None
    changed: bool = False
    moved: int = 0

    @property
    def importable(self) -> bool:
        return self.status != "error" and self.events is not None

    def describe(self) -> str:
        return " · ".join(self.notes)


def position_fit(events: list[Event], step_ms: float, tolerance_ms: float) -> float:
    """Share of notes within ``tolerance_ms`` of a grid anchored at the first note."""
    origin = events[0][0]
    hits = 0
    for time, _ in events:
        offset = (time - origin) % step_ms
        hits += min(offset, step_ms - offset) <= tolerance_ms
    return hits / len(events)


def refine_step(events: list[Event], step_ms: float, spread: float = .04) -> float:
    """Best grid step near ``step_ms``, measured on note positions, not gaps.

    Jitter does not accumulate in positions, so the fitted step does not drift
    over a long song the way an average gap does.
    """
    origin = events[0][0]

    def cost(step: float) -> float:
        total = 0.0
        for time, _ in events:
            offset = (time - origin) % step
            total += min(offset, step - offset)
        return total

    low, high = step_ms * (1 - spread), step_ms * (1 + spread)
    best = min((low + (high - low) * i / 400 for i in range(401)), key=cost)
    whole = round(best)
    # Sheets are written in whole milliseconds; prefer that step when it fits as well.
    if abs(best - whole) < .2 and (position_fit(events, whole, JITTER_TOLERANCE_MS)
                                   >= position_fit(events, best, JITTER_TOLERANCE_MS)):
        return float(whole)
    return round(best, 2)


def classify_timing(events: list[Event]) -> tuple[str, GridInfo | None]:
    """``exact`` on a grid, ``jitter`` near one, ``unclear`` or ``short``."""
    if len(events) < 5:
        return "short", None
    exact = detect_grid(events, EXACT_TOLERANCE_MS)
    if exact and exact.on_grid >= .98:
        return "exact", exact
    for candidate in grid_candidates(events, JITTER_TOLERANCE_MS, bucket_ms=10):
        # A fine grid fits almost anything within the jitter tolerance; only a
        # coarse one is evidence of a real beat.
        if candidate.step_ms < MIN_JITTER_STEP_MS:
            continue
        step = refine_step(events, candidate.step_ms)
        if position_fit(events, step, JITTER_TOLERANCE_MS) >= .98:
            return "jitter", GridInfo(step, grid_ratio(events, step, EXACT_TOLERANCE_MS))
    return "unclear", exact


def collect_files(sources: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for source in sources:
        source = Path(source)
        if source.is_dir():
            files.extend(path for path in sorted(source.rglob("*"))
                         if path.is_file() and path.suffix.lower() in SHEET_SUFFIXES)
        elif source.is_file() and source.suffix.lower() in SHEET_SUFFIXES:
            files.append(source)
    return files


def analyze_file(path: Path, supported_keys: Iterable[str], *, merge: bool = True,
                 fix_timing: bool = True) -> BatchItem:
    item = BatchItem(path, title=path.stem)
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise RepositoryError(tr("File lớn hơn 5 MB."))
        sheet = SheetRepository._parse(_read_json(path), source_name=path.name)
    except (OSError, RepositoryError) as exc:
        item.status = "error"
        hint = tr(" Nếu đây là sheet chữ, hãy dùng “Nhập sheet chữ…”.") \
            if path.suffix.lower() == ".txt" else ""
        item.notes.append(tr("Lỗi: {error}").format(error=exc) + hint)
        return item
    item.title = sheet.title
    events = normalize((note.time, note.keys) for note in sheet.notes)
    if not events:
        item.status = "error"
        item.notes.append(tr("Sheet không có nốt nào."))
        return item
    if has_layers(events):
        if merge:
            events = merge_layers(events)
            item.changed = True
            item.notes.append(tr("Đã gộp lớp 2Key/3Key"))
        else:
            item.notes.append(tr("Còn lớp 2Key/3Key"))
    timing, grid = classify_timing(events)
    if timing == "exact":
        item.notes.append(tr("Nhịp chuẩn"))
    elif timing == "jitter" and grid is not None:
        if fix_timing:
            events, item.moved = quantize(events, grid.step_ms)
            item.changed = item.changed or item.moved > 0
            item.notes.append(tr("Đã chỉnh nhịp {count} nốt theo lưới {step} ms").format(
                count=item.moved, step=f"{grid.step_ms:g}"))
        else:
            item.notes.append(tr("Nhịp lệch nhẹ, chưa chỉnh"))
    elif timing == "unclear":
        item.status = "review"
        item.notes.append(tr("Nhịp không theo lưới rõ ràng — nên nghe thử"))
    supported = set(supported_keys)
    missing = sorted({key for _, keys in events for key in keys if key not in supported})
    if missing:
        item.status = "review"
        item.notes.append(tr("Phím chưa hỗ trợ: {keys}").format(keys=", ".join(missing[:5])))
    if item.status == "ok" and item.changed:
        item.status = "changed"
    item.events = events
    return item


def analyze(sources: Iterable[Path], supported_keys: Iterable[str], *, merge: bool = True,
            fix_timing: bool = True) -> list[BatchItem]:
    keys = list(supported_keys)
    return [analyze_file(path, keys, merge=merge, fix_timing=fix_timing)
            for path in collect_files(sources)]
