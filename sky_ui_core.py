"""Sky Instrument Console — a PySide6 successor to the legacy Tk UI.

The old interface remains untouched. Playback runs in a worker and communicates
with widgets exclusively through Qt signals.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

from PySide6.QtCore import (
    QElapsedTimer, QObject, QPointF, QRectF, QSize, Qt, QThread, QTimer, Signal, Slot,
)
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSizePolicy, QSlider, QStackedWidget, QVBoxLayout,
    QWidget,
)

from macro_core import MacroPlayer

APP_DIR = Path(__file__).resolve().parent
_SOURCE_CHECKOUT = (APP_DIR / "pyproject.toml").is_file()
USER_DATA_DIR = (
    APP_DIR if _SOURCE_CHECKOUT else
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    / "SkyInstrumentConsole"
)
_SOURCE_SHEETS_DIR = APP_DIR / "sheets"
_INSTALLED_SHEETS_DIR = Path(sys.prefix) / "share" / "sky-macro-player" / "sheets"
SHEETS_DIR = (
    _SOURCE_SHEETS_DIR if _SOURCE_SHEETS_DIR.is_dir()
    else _INSTALLED_SHEETS_DIR
)
FAVORITES_FILE = USER_DATA_DIR / "favorites.json"


def migrate_legacy_user_data(
    *, data_dir: Path = USER_DATA_DIR,
    legacy_dirs: tuple[Path, ...] | None = None,
) -> tuple[Path, ...]:
    """Copy legacy runtime files once; never overwrite an existing user file."""
    if data_dir.resolve() == APP_DIR.resolve():
        return ()
    sources = legacy_dirs or (APP_DIR, Path.cwd())
    copied: list[Path] = []
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        for name in ("hotkeys.json", "favorites.json"):
            destination = data_dir / name
            if destination.exists():
                continue
            source = next(
                (folder / name for folder in sources if (folder / name).is_file()),
                None,
            )
            if source is not None and source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
                copied.append(destination)
    except OSError as exc:
        raise RuntimeError(f"Không thể chuyển dữ liệu người dùng: {exc}") from exc
    return tuple(copied)


class Tokens:
    CLOUD_INK = "#101722"
    DEEP_SLATE = "#192536"
    LIFTED_SLATE = "#24344A"
    MOON_MIST = "#E7EFF7"
    HUSHED_BLUE = "#91A5BA"
    SKY_BLUE = "#82CFFF"
    APRICOT = "#FFB287"
    DANGER = "#FF7A86"
    BORDER = "#34485F"
    DISPLAY = "Bahnschrift SemiCondensed"
    BODY = "Segoe UI Variable"
    UTILITY = "Cascadia Mono"


STYLE = f"""
* {{ font-family: '{Tokens.BODY}'; font-size: 13px; color: {Tokens.MOON_MIST}; }}
QMainWindow, QWidget#appRoot {{ background: {Tokens.CLOUD_INK}; }}
QWidget#rail, QWidget#queuePanel, QFrame#playbackDock {{ background: {Tokens.DEEP_SLATE}; }}
QLabel#brand {{ font-family: '{Tokens.DISPLAY}'; font-size: 22px; font-weight: 600; }}
QLabel#eyebrow {{ color: {Tokens.SKY_BLUE}; font-family: '{Tokens.UTILITY}'; font-size: 10px; }}
QLabel#pageTitle {{ font-family: '{Tokens.DISPLAY}'; font-size: 30px; font-weight: 600; }}
QLabel#muted {{ color: {Tokens.HUSHED_BLUE}; }}
QPushButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px;
 padding: 8px 12px; text-align: left; }}
QPushButton:hover {{ background: {Tokens.LIFTED_SLATE}; }}
QPushButton:focus {{ border: 2px solid {Tokens.SKY_BLUE}; }}
QPushButton[nav="true"]:checked {{ background: {Tokens.LIFTED_SLATE}; color: {Tokens.SKY_BLUE}; }}
QPushButton[primary="true"] {{ background: {Tokens.APRICOT}; color: {Tokens.CLOUD_INK};
 font-weight: 700; text-align: center; }}
QPushButton[danger="true"] {{ color: {Tokens.DANGER}; border-color: #673846; text-align: center; }}
QPushButton[compact="true"] {{ padding: 6px 9px; text-align: center; }}
QLineEdit, QComboBox {{ background: {Tokens.DEEP_SLATE}; border: 1px solid {Tokens.BORDER};
 border-radius: 9px; padding: 9px 11px; selection-background-color: {Tokens.SKY_BLUE}; }}
QLineEdit:focus, QComboBox:focus {{ border: 2px solid {Tokens.SKY_BLUE}; }}
QListWidget {{ background: transparent; border: 0; outline: 0; }}
QListWidget::item {{ border-bottom: 1px solid #26384C; padding: 10px 8px; }}
QListWidget::item:hover {{ background: #1D2C3E; }}
QListWidget::item:selected {{ background: {Tokens.LIFTED_SLATE}; border-left: 3px solid {Tokens.SKY_BLUE}; }}
QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: {Tokens.BORDER}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; margin: -5px 0; background: {Tokens.SKY_BLUE}; border-radius: 7px; }}
"""


@dataclass(frozen=True, slots=True)
class Song:
    path: Path
    title: str
    favorite: bool = False

    @property
    def identity(self) -> str:
        try:
            return str(self.path.resolve().relative_to(APP_DIR)).replace("/", "\\")
        except ValueError:
            return str(self.path.resolve())


class FavoritesStore(Protocol):
    def load(self) -> set[str]: ...
    def save(self, paths: Iterable[str]) -> None: ...


class JsonFavoritesStore:
    """Compatibility adapter for the current favorites.json record shape."""

    def __init__(self, path: Path = FAVORITES_FILE) -> None:
        self.path = path

    def load(self) -> set[str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        if not isinstance(raw, list):
            return set()
        answer = set()
        for value in raw:
            candidate = value.get("path") if isinstance(value, dict) else value
            if isinstance(candidate, str):
                answer.add(candidate.replace("/", "\\"))
        return answer

    def save(self, paths: Iterable[str]) -> None:
        records = [{"name": Path(path).name, "type": "JSON", "path": path}
                   for path in sorted(set(paths))]
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(records, ensure_ascii=False, indent=4), encoding="utf-8")
        temporary.replace(self.path)


class SheetLibrary:
    def __init__(self, sheets_dir: Path = SHEETS_DIR, favorites: FavoritesStore | None = None) -> None:
        self.sheets_dir = sheets_dir
        self.favorites = favorites or JsonFavoritesStore()

    def songs(self) -> list[Song]:
        favorites = {value.casefold() for value in self.favorites.load()}
        paths = [*self.sheets_dir.glob("*.txt"), *self.sheets_dir.glob("*.json")]
        result = []
        for path in sorted(paths, key=lambda item: item.stem.casefold()):
            relative = str(path.resolve().relative_to(APP_DIR)).replace("/", "\\")
            result.append(Song(path, path.stem, relative.casefold() in favorites))
        return result


def load_sheet(path: Path) -> tuple[object, list[int], int]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    container = data[0] if isinstance(data, list) and data else data
    if not isinstance(container, dict) or not isinstance(container.get("songNotes"), list):
        raise ValueError("Tệp không có danh sách songNotes hợp lệ.")
    moments = sorted({int(note["time"]) for note in container["songNotes"]
                      if isinstance(note, dict) and isinstance(note.get("time"), (int, float))})
    return data, moments, moments[-1] if moments else 0


class PlaybackWorker(QObject):
    prepared = Signal(list, int)
    completed = Signal(bool)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, song: Song, layout: str, stop: threading.Event,
                 pause: threading.Event, countdown: int) -> None:
        super().__init__()
        self.song, self.layout = song, layout
        self.stop, self.pause, self.countdown = stop, pause, countdown

    @Slot()
    def run(self) -> None:
        try:
            data, moments, duration = load_sheet(self.song.path)
            self.prepared.emit(moments, duration)
            player = MacroPlayer()
            player.set_key_layout(self.layout)
            self.completed.emit(bool(player.play_json_sheet(
                data, self.stop, self.pause, self.countdown)))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class PlaybackController(QObject):
    state_changed = Signal(str)
    song_changed = Signal(object)
    timeline_ready = Signal(list, int)
    error = Signal(str)
    finished = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: PlaybackWorker | None = None
        self._stop, self._pause = threading.Event(), threading.Event()
        self._result = False
        self.state, self.current_song = "idle", None
        self.layout_name, self.countdown = "old", 3

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def play(self, song: Song) -> bool:
        if self.busy:
            return False
        self._stop, self._pause = threading.Event(), threading.Event()
        self._result, self.current_song = False, song
        self._set_state("playing")
        self.song_changed.emit(song)
        thread = QThread(self)
        worker = PlaybackWorker(song, self.layout_name, self._stop, self._pause, self.countdown)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.prepared.connect(self.timeline_ready)
        worker.completed.connect(self._capture_result)
        worker.failed.connect(self.error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        thread.start()
        return True

    @Slot(bool)
    def _capture_result(self, value: bool) -> None:
        self._result = value

    @Slot()
    def _thread_finished(self) -> None:
        result = self._result
        self._thread = self._worker = None
        self._set_state("idle")
        self.finished.emit(result)

    def toggle_pause(self) -> None:
        if self.state == "playing":
            self._pause.set(); self._set_state("paused")
        elif self.state == "paused":
            self._pause.clear(); self._set_state("playing")

    def stop(self) -> None:
        if self.busy:
            self._stop.set(); self._pause.clear(); self._set_state("stopping")

    def _set_state(self, value: str) -> None:
        self.state = value
        self.state_changed.emit(value)


class NoteRunway(QWidget):
    """Signature timeline: notes travel toward a warm vertical playhead."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(74)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Tiến trình nốt nhạc")
        self._moments, self._duration, self._elapsed = [], 1, 0
        self._elapsed_before_run = 0
        self._playing = self._reduced_motion = False
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_timeline(self, moments: list[int], duration: int) -> None:
        self._moments, self._duration, self._elapsed = moments, max(1, duration), 0
        self._elapsed_before_run = 0
        self._clock.invalidate()
        self.update()

    def set_progress(self, elapsed: int) -> None:
        """Reconcile visual interpolation with an authoritative engine position."""
        self._elapsed = max(0, min(self._duration, int(elapsed)))
        self._elapsed_before_run = self._elapsed
        if self._playing:
            self._clock.restart()
        self.update()

    def set_playing(self, value: bool) -> None:
        if value == self._playing:
            return
        if self._playing:
            self._sync_elapsed()
            self._elapsed_before_run = self._elapsed
        self._playing = value
        if value:
            self._clock.restart()
            self._timer.setInterval(33)
            if not self._reduced_motion:
                self._timer.start()
        else:
            self._clock.invalidate()
            self._timer.stop()
        self.update()

    def set_reduced_motion(self, value: bool) -> None:
        self._reduced_motion = value
        if value:
            self._timer.stop()
        elif self._playing:
            self._timer.start()

    def reset(self) -> None:
        self._timer.stop()
        self._clock.invalidate()
        self._elapsed = self._elapsed_before_run = 0
        self._playing = False
        self.update()

    def _tick(self) -> None:
        self._sync_elapsed()
        self.update()

    def _sync_elapsed(self) -> None:
        """Derive progress from a monotonic clock so delayed paint ticks do not drift."""
        if self._playing and self._clock.isValid():
            self._elapsed = min(
                self._duration,
                self._elapsed_before_run + self._clock.elapsed(),
            )

    def sizeHint(self) -> QSize:
        return QSize(500, 74)

    def paintEvent(self, event) -> None:
        self._sync_elapsed()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(8, 8, -8, -8)
        gradient = QLinearGradient(bounds.topLeft(), bounds.topRight())
        gradient.setColorAt(0, QColor(Tokens.DEEP_SLATE)); gradient.setColorAt(1, QColor("#1D3045"))
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(bounds), 10, 10)
        center = bounds.center().y()
        painter.setPen(QPen(QColor(Tokens.BORDER), 1)); painter.drawLine(bounds.left()+12, int(center), bounds.right()-12, int(center))
        progress, playhead = self._elapsed / self._duration, bounds.left() + bounds.width() * .26
        painter.setPen(QPen(QColor(Tokens.APRICOT), 2)); painter.drawLine(int(playhead), bounds.top()+9, int(playhead), bounds.bottom()-9)
        painter.setPen(Qt.PenStyle.NoPen)
        for index, moment in enumerate(self._moments):
            x = playhead + (moment / self._duration - progress) * bounds.width() * .72
            if bounds.left()+8 <= x <= bounds.right()-8:
                color = QColor(Tokens.SKY_BLUE); color.setAlphaF(max(.2, 1-abs(x-playhead)/max(1,bounds.width())*1.8))
                painter.setBrush(color); radius = 3.5 if abs(x-playhead) < 8 else 2.5
                painter.drawEllipse(QPointF(x, center + ((index % 5)-2)*7), radius, radius)
