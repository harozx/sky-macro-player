"""Text sheets ("sheet chữ") → playable events.

Three notations shared by Sky players are understood:

* **Số** (numbered notation): ``1 2 3 5 6 1' 2'`` — 1–7 are Đô…Si.
* **Đô Rê Mi**: ``Đô Rê Mi Son La Đô'`` (accents optional, ``Sol``/``Ti`` too).
* **Chữ phím**: the in-game keys of the chosen layout, e.g. ``y u i o p``.

Common rules: ``'`` (or ``’ ^ +``) raises a note one octave, ``,`` lowers it in
number/solfège mode; ``(…)`` or ``[…]`` is a chord; ``-``/``_`` adds one rest
step (``0`` too in number mode); ``|`` bar lines are ignored; each line can end
with extra rest steps. Every symbol is one step of ``step_ms``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping

from .i18n import tr
from .search import fold_text

FORMATS = ("auto", "number", "solfege", "keys")
_SOLFEGE = {"do": 1, "re": 2, "mi": 3, "fa": 4, "son": 5, "sol": 5, "so": 5, "la": 6,
            "si": 7, "ti": 7}
_UP = "'" + chr(0x2019) + "^+"  # apostrophe, typographic apostrophe
_REST = "-_"
_OPEN, _CLOSE = "([", ")]"


@dataclass
class ParseIssue:
    line: int
    column: int
    token: str
    message: str

    def describe(self) -> str:
        return tr("Dòng {line}, cột {column}: “{token}” — {message}").format(
            line=self.line, column=self.column, token=self.token, message=self.message)


@dataclass
class TextSheet:
    events: list[tuple[float, tuple[str, ...]]] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)
    detected_format: str = "number"
    folded: int = 0

    @property
    def note_count(self) -> int:
        return sum(len(keys) for _, keys in self.events)


def detect_format(text: str) -> str:
    words = re.findall(r"[^\W\d_]+", text)
    folded = [fold_text(word) for word in words]
    if folded and sum(word in _SOLFEGE for word in folded) >= max(2, len(folded) * .6):
        return "solfege"
    letters = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    return "number" if digits >= letters else "keys"


def _degree_to_index(degree: int, octave: int, base_octave: int) -> tuple[int, bool]:
    """Map degree 1–7 and octave shift to key 0–14; fold back if out of range."""
    index = (degree - 1) + 7 * (octave + base_octave)
    folded = False
    while index > 14:
        index -= 7
        folded = True
    while index < 0:
        index += 7
        folded = True
    return index, folded


def _tokenize_line(line: str, mode: str):
    """Yield (column, kind, value) where kind is note/rest/open/close/skip/bad."""
    i = 0
    while i < len(line):
        ch = line[i]
        column = i + 1
        if ch.isspace() or ch == "|":
            i += 1
            continue
        if ch in _OPEN:
            yield column, "open", ch
            i += 1
            continue
        if ch in _CLOSE:
            yield column, "close", ch
            i += 1
            continue
        if mode == "keys":
            if ch in _REST:
                yield column, "rest", ch
            else:
                yield column, "note", ch
            i += 1
            continue
        if ch in _REST or (mode == "number" and ch == "0"):
            yield column, "rest", ch
            i += 1
            continue
        if mode == "number":
            match = re.match(r"([1-7])([" + re.escape(_UP) + r",]*)", line[i:])
        else:
            match = re.match(r"([^\W\d_]+)([" + re.escape(_UP) + r",]*)", line[i:])
        if match:
            yield column, "note", match.group(0)
            i += len(match.group(0))
            continue
        yield column, "bad", ch
        i += 1


def parse_text_sheet(text: str, *, fmt: str = "auto", step_ms: float = 500,
                     key_map: Mapping[str, str] | None = None, base_octave: int = 0,
                     line_rest_steps: int = 0) -> TextSheet:
    """Parse ``text``; ``key_map`` is the layout map (``1Key0`` → ``y``) for key mode."""
    mode = detect_format(text) if fmt == "auto" else fmt
    if mode not in FORMATS[1:]:
        raise ValueError(f"Unknown text sheet format: {fmt}")
    reverse = {key.casefold(): code for code, key in (key_map or {}).items()}
    result = TextSheet(detected_format=mode)
    step = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        chord: list[str] | None = None
        chord_column = 0
        had_content = False
        for column, kind, value in _tokenize_line(line, mode):
            if kind == "open":
                if chord is not None:
                    result.issues.append(ParseIssue(line_number, column, value,
                                                    tr("hợp âm lồng nhau")))
                chord, chord_column = [], column
                continue
            if kind == "close":
                if chord is None:
                    result.issues.append(ParseIssue(line_number, column, value,
                                                    tr("thiếu dấu mở hợp âm")))
                    continue
                if chord:
                    result.events.append((step * step_ms, tuple(dict.fromkeys(chord))))
                step += 1
                chord = None
                had_content = True
                continue
            if kind == "rest":
                if chord is None:
                    step += 1
                    had_content = True
                continue
            if kind == "bad":
                result.issues.append(ParseIssue(line_number, column, value,
                                                tr("ký hiệu không hiểu")))
                continue
            code = _note_code(value, mode, reverse, base_octave, result)
            if code is None:
                result.issues.append(ParseIssue(
                    line_number, column, value,
                    tr("không có phím này trong bộ phím đang dùng") if mode == "keys"
                    else tr("không phải nốt Đô Rê Mi")))
                continue
            if chord is not None:
                chord.append(code)
            else:
                result.events.append((step * step_ms, (code,)))
                step += 1
                had_content = True
        if chord is not None:
            result.issues.append(ParseIssue(line_number, chord_column, "(",
                                            tr("hợp âm chưa đóng")))
        if had_content:
            step += line_rest_steps
    return result


def _note_code(token: str, mode: str, reverse: Mapping[str, str], base_octave: int,
               result: TextSheet) -> str | None:
    if mode == "keys":
        return reverse.get(token.casefold())
    marks = re.search(r"[" + re.escape(_UP) + r",]*$", token)
    suffix = marks.group(0) if marks else ""
    body = token[: len(token) - len(suffix)]
    octave = sum(1 for ch in suffix if ch in _UP) - suffix.count(",")
    if mode == "number":
        degree = int(body)
    else:
        degree = _SOLFEGE.get(fold_text(body), 0)
        if not degree:
            return None
    index, folded = _degree_to_index(degree, octave, base_octave)
    result.folded += int(folded)
    return f"1Key{index}"
