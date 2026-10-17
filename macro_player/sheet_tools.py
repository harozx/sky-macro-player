"""Pure sheet transformations: merge layers, cut, quantize, transpose, tempo.

All functions take and return ``[(time_ms, keys), ...]`` events and never touch
files. The editor applies them in a fixed order (see ``EditOptions``) and saves
the result as a new sheet.
"""

from __future__ import annotations

import collections
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .i18n import tr

Event = tuple[float, tuple[str, ...]]
_KEY = re.compile(r"^(\d+)Key(\d+)$")
KEY_COUNT = 15
OCTAVE = 7  # Sky's 15 keys are a C-major scale: 7 steps make an octave.


def normalize(events: Iterable[tuple[float, Sequence[str]]]) -> list[Event]:
    """Sort by time, merge events at the same time and drop duplicate keys."""
    grouped: dict[float, list[str]] = {}
    for time, keys in events:
        bucket = grouped.setdefault(float(time), [])
        for key in keys:
            if key not in bucket:
                bucket.append(key)
    return [(time, tuple(keys)) for time, keys in sorted(grouped.items()) if keys]


def merge_layers(events: Iterable[Event]) -> list[Event]:
    """Map ``2Key5``/``3Key5`` onto ``1Key5``."""
    result = []
    for time, keys in events:
        mapped = []
        for key in keys:
            match = _KEY.match(key)
            mapped.append(f"1Key{match.group(2)}" if match else key)
        result.append((time, tuple(mapped)))
    return normalize(result)


def has_layers(events: Iterable[Event]) -> bool:
    return any((m := _KEY.match(key)) and m.group(1) != "1"
               for _, keys in events for key in keys)


def cut(events: Iterable[Event], start_ms: float, end_ms: float | None,
        lead_ms: float = 0) -> list[Event]:
    """Keep ``start_ms <= time <= end_ms`` and move the section to ``lead_ms``."""
    kept = [(time, keys) for time, keys in events
            if time >= start_ms and (end_ms is None or time <= end_ms)]
    if not kept:
        return []
    shift = kept[0][0] - lead_ms
    return [(time - shift, keys) for time, keys in kept]


def gaps(events: Sequence[Event]) -> list[float]:
    times = [time for time, _ in events]
    return [b - a for a, b in zip(times, times[1:], strict=False) if b - a > 0]


@dataclass(frozen=True)
class GridInfo:
    step_ms: float
    on_grid: float  # share of note gaps that are whole multiples of the step


SUBDIVISIONS = (1, 2, 3, 4, 6, 8)


def grid_candidates(events: Sequence[Event], tolerance_ms: float = 3) -> list[GridInfo]:
    """The most common gap and its subdivisions, each with its on-grid share."""
    spacing = [round(gap) for gap in gaps(events)]
    if len(spacing) < 4:
        return []
    common = collections.Counter(spacing).most_common(6)
    floor = max(2, common[0][1] * .15)
    frequent = [gap for gap, count in common if count >= floor]
    # With no repeated gap (short hand recordings) fall back to the most common one.
    base = min(frequent) if frequent else common[0][0]
    if base <= 0:
        return []
    result = []
    for division in SUBDIVISIONS:
        step = base / division
        if step >= 20:
            result.append(GridInfo(step, grid_ratio(events, step, tolerance_ms)))
    return result


def detect_grid(events: Sequence[Event], tolerance_ms: float = 3,
                good_enough: float = .98) -> GridInfo | None:
    """Coarsest grid that explains almost every gap, else the best candidate.

    Many sheets use eighth or sixteenth notes; their beat grid looks "off" while
    a finer subdivision fits exactly, and snapping to the coarse beat would
    destroy the rhythm.
    """
    candidates = grid_candidates(events, tolerance_ms)
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.on_grid >= good_enough:
            return candidate
    return max(candidates, key=lambda item: (round(item.on_grid, 2), item.step_ms))


def grid_ratio(events: Sequence[Event], step_ms: float, tolerance_ms: float = 3) -> float:
    spacing = gaps(events)
    if not spacing or step_ms <= 0:
        return 0.0
    hits = sum(1 for gap in spacing
               if abs(gap / step_ms - round(gap / step_ms)) * step_ms <= tolerance_ms)
    return hits / len(spacing)


def quantize(events: Sequence[Event], step_ms: float) -> tuple[list[Event], int]:
    """Snap every note to a grid anchored at the first note; return moved count."""
    if step_ms <= 0 or not events:
        return list(events), 0
    origin = events[0][0]
    moved = 0
    snapped = []
    for time, keys in events:
        target = origin + round((time - origin) / step_ms) * step_ms
        if abs(target - time) > .5:
            moved += 1
        snapped.append((float(round(target)), keys))
    return normalize(snapped), moved


def transpose(events: Iterable[Event], steps: int) -> tuple[list[Event], int]:
    """Shift by scale steps; notes leaving the 15 keys fold back by an octave."""
    folded = 0
    result = []
    for time, keys in events:
        shifted = []
        for key in keys:
            match = _KEY.match(key)
            if not match:
                shifted.append(key)
                continue
            index = int(match.group(2)) + steps
            if not 0 <= index < KEY_COUNT:
                folded += 1
                while index >= KEY_COUNT:
                    index -= OCTAVE
                while index < 0:
                    index += OCTAVE
            shifted.append(f"{match.group(1)}Key{index}")
        result.append((time, tuple(shifted)))
    return normalize(result), folded


def change_tempo(events: Iterable[Event], percent: float) -> list[Event]:
    """``percent`` 120 plays 20% faster; times are rounded to whole ms."""
    factor = 100.0 / max(1.0, float(percent))
    return normalize((float(round(time * factor)), keys) for time, keys in events)


@dataclass(frozen=True)
class EditOptions:
    merge_layers: bool = False
    start_ms: float = 0
    end_ms: float | None = None
    quantize_step_ms: float | None = None
    transpose_steps: int = 0
    tempo_percent: float = 100


@dataclass
class EditReport:
    notes_before: int = 0
    notes_after: int = 0
    duration_before: float = 0
    duration_after: float = 0
    grid_before: float | None = None
    grid_after: float | None = None
    moved: int = 0
    folded: int = 0
    layered_left: bool = False
    warnings: list[str] = field(default_factory=list)


def note_count(events: Sequence[Event]) -> int:
    return sum(len(keys) for _, keys in events)


def apply_edits(source: Sequence[Event], options: EditOptions) -> tuple[list[Event], EditReport]:
    """Merge layers → cut → quantize → transpose → tempo, with a report."""
    events = normalize(source)
    report = EditReport(notes_before=note_count(events),
                        duration_before=events[-1][0] if events else 0)
    detected = detect_grid(events)
    report.grid_before = detected.on_grid if detected else None
    if options.merge_layers:
        events = merge_layers(events)
    if options.start_ms > 0 or options.end_ms is not None:
        # A section cut from the middle starts at 0; trimming only the end keeps
        # the original lead-in.
        lead = events[0][0] if events and options.start_ms <= 0 else 0
        events = cut(events, options.start_ms, options.end_ms, lead_ms=lead)
    step = options.quantize_step_ms
    if step:
        events, report.moved = quantize(events, step)
    if options.transpose_steps:
        events, report.folded = transpose(events, options.transpose_steps)
    if options.tempo_percent != 100:
        events = change_tempo(events, options.tempo_percent)
        if step:
            step = step * 100.0 / options.tempo_percent
    report.notes_after = note_count(events)
    report.duration_after = events[-1][0] if events else 0
    if events:
        grid = grid_ratio(events, step) if step else None
        if grid is None:
            info = detect_grid(events)
            grid = info.on_grid if info else None
        report.grid_after = grid
    report.layered_left = has_layers(events)
    if not events:
        report.warnings.append(tr("Đoạn đã chọn không còn nốt nào."))
    if report.layered_left:
        report.warnings.append(
            tr("Bản mới vẫn còn lớp 2Key/3Key; bật “Gộp lớp” để phát được."))
    if report.folded:
        report.warnings.append(
            tr("{count} nốt vượt 15 phím đã được gập quãng tám.").format(count=report.folded))
    if report.notes_after < report.notes_before and not options.end_ms and not options.start_ms:
        merged = report.notes_before - report.notes_after
        report.warnings.append(
            tr("{count} nốt trùng thời điểm và phím đã được gộp.").format(count=merged))
    return events, report


def to_sheet_payload(title: str, events: Sequence[Event], *, bpm: int | None = None,
                     source: str | None = None) -> list[dict]:
    """Sky Music sheet format: a one-item list holding ``songNotes``."""
    payload = {
        "name": title,
        "author": "Sky Macro Player",
        "isComposed": True,
        "bpm": int(bpm) if bpm else 240,
        "bitsPerPage": 16,
        "pitchLevel": 0,
        "songNotes": [{"time": int(round(time)), "key": key}
                      for time, keys in events for key in keys],
    }
    if source:
        payload["editedFrom"] = source
    return [payload]


def save_new_sheet(folder: Path, file_name: str, payload: list[dict]) -> Path:
    """Write a new UTF-8 sheet; an existing file is never replaced."""
    stem = Path(file_name).stem.strip() or "Sheet"
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem)[:120]
    candidate, index = folder / f"{stem}.json", 2
    while candidate.exists():
        candidate = folder / f"{stem} ({index}).json"
        index += 1
    folder.mkdir(parents=True, exist_ok=True)
    with candidate.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    return candidate
