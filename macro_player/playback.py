"""Single playback controller: one worker thread per session, Qt signals only.

States: idle, countdown, starting, playing, paused, focus_paused, stopping,
error. Every worker signal carries its session id so callbacks from an older
session can never change the state of a newer one.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from .engine import MacroPlayer
from .library import Song
from .repositories import SheetRepository

Prepared = tuple[list, list[int], int]
DEFAULT_KEY_MAP = dict(MacroPlayer.KEY_LAYOUTS["old"]["json_map"])


def load_song_events(song: Song) -> Prepared:
    """Default loader: parse a sheet file without any layer policy."""
    sheet = SheetRepository(song.path.parent).load(song.path.name)
    events = [(note.time, tuple(note.keys)) for note in sheet.notes]
    moments = sorted({int(note.time) for note in sheet.notes})
    return events, moments, moments[-1] if moments else 0


class NullKeyboard:
    """Preview backend: records nothing and never reaches the operating system."""

    def press(self, key) -> None:
        pass

    def release(self, key) -> None:
        pass


class SpeedRef:
    """Shared speed value; the engine reads it live between notes."""

    def __init__(self, value: float = 1.0) -> None:
        self.value = value

    def __float__(self) -> float:
        return float(self.value)


class PlaybackWorker(QObject):
    prepared = Signal(list, int)
    countdown = Signal(int)
    playback_started = Signal(int)
    progress = Signal(int, int)
    keys_pressed = Signal(int, list)
    completed = Signal(bool)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, song: Song, *, loader: Callable[[Song], Prepared],
                 key_map: dict[str, str], stop: threading.Event,
                 pause: threading.Event, countdown: int,
                 input_guard: Callable[[], bool] | None = None, session: int = 0,
                 speed: SpeedRef | None = None, start_ms: int = 0,
                 loop_range: tuple[int, int] | None = None,
                 preview: bool = False) -> None:
        super().__init__()
        self.song, self.loader, self.key_map = song, loader, key_map
        self.stop, self.pause, self.countdown_seconds = stop, pause, countdown
        self.input_guard = None if preview else input_guard
        self.session = session
        self.speed = speed or SpeedRef()
        self.start_ms, self.loop_range, self.preview = start_ms, loop_range, preview

    def _input_allowed(self) -> bool:
        if self.input_guard is None:
            return True
        try:
            return bool(self.input_guard())
        except Exception:
            return False

    def _run_countdown(self) -> bool:
        remaining = float(self.countdown_seconds)
        last_tick = time.monotonic()
        last_displayed = None
        while remaining > 0:
            if self.stop.is_set():
                return False
            now = time.monotonic()
            if self.pause.is_set() or not self._input_allowed():
                last_tick = now
                self.stop.wait(0.05)
                continue
            remaining = max(0.0, remaining - (now - last_tick))
            last_tick = now
            displayed = max(1, int(remaining + 0.999))
            if displayed != last_displayed:
                self.countdown.emit(displayed)
                last_displayed = displayed
            self.stop.wait(min(0.05, remaining))
        return not self.stop.is_set()

    @Slot()
    def run(self) -> None:
        try:
            events, moments, duration = self.loader(self.song)
            self.prepared.emit(moments, duration)
            if not self._run_countdown():
                self.completed.emit(False)
                return
            self.playback_started.emit(self.session)
            player = MacroPlayer(
                controller=NullKeyboard() if self.preview else None,
                input_guard=self.input_guard,
                progress_callback=lambda elapsed: self.progress.emit(self.session, int(elapsed)),
                key_callback=lambda keys: self.keys_pressed.emit(self.session, list(keys)),
                speed=self.speed,
            )
            player.json_key_map = dict(self.key_map)
            if self.loop_range is not None:
                start, end = self.loop_range
                # A loop only ends through Stop, so it never counts as completed.
                while not self.stop.is_set():
                    if not player.play_events(events, self.stop, self.pause, 0,
                                              start_ms=start, end_ms=end):
                        break
                self.completed.emit(False)
                return
            completed = bool(player.play_events(
                events, self.stop, self.pause, 0, start_ms=self.start_ms))
            if completed:
                self.progress.emit(self.session, duration)
            self.completed.emit(completed)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class PlaybackController(QObject):
    state_changed = Signal(str)
    song_changed = Signal(object)
    timeline_ready = Signal(list, int)
    countdown_changed = Signal(int)
    progress_changed = Signal(int)
    keys_pressed = Signal(list)
    playback_started = Signal(object)
    error = Signal(str)
    finished = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: PlaybackWorker | None = None
        self._stop, self._pause = threading.Event(), threading.Event()
        self._result = False
        self._failure: str | None = None
        self._state_before_focus_pause = "playing"
        self._session_counter = self._active_session = 0
        self._playback_has_started = False
        self.input_guard: Callable[[], bool] | None = None
        self.state = "idle"
        self.current_song: Song | None = None
        self.layout_name, self.countdown = "old", 3
        self.key_map: dict[str, str] = dict(DEFAULT_KEY_MAP)
        self.loader: Callable[[Song], Prepared] = load_song_events
        self.speed_ref = SpeedRef()
        self.start_ms = 0
        self.loop_range: tuple[int, int] | None = None
        self.preview = False

    @property
    def speed(self) -> float:
        return float(self.speed_ref.value)

    @speed.setter
    def speed(self, value: float) -> None:
        self.speed_ref.value = float(value)

    def set_layout(self, name: str, key_map: dict[str, str]) -> None:
        self.layout_name, self.key_map = name, dict(key_map)

    @property
    def busy(self) -> bool:
        if self._thread is None:
            return False
        try:
            return self._thread.isRunning()
        except RuntimeError:
            # Qt may already have completed deleteLater while the Python
            # wrapper is retained until the next playback session.
            return False

    def play(self, song: Song) -> bool:
        if self.busy:
            return False
        # Do not drop the final Python reference from inside QThread.finished:
        # on PySide that can destroy the signal sender while Qt is still
        # dispatching it. Replace the completed session only when starting the
        # next one, after the finished callback has fully unwound.
        self._thread = self._worker = None
        self._stop, self._pause = threading.Event(), threading.Event()
        self._result, self._failure, self.current_song = False, None, song
        self._session_counter += 1
        session = self._active_session = self._session_counter
        self._playback_has_started = False
        self._set_state("countdown" if self.countdown else "starting")
        self.song_changed.emit(song)
        thread = QThread(self)
        worker = PlaybackWorker(
            song, loader=self.loader, key_map=self.key_map, stop=self._stop,
            pause=self._pause, countdown=self.countdown, input_guard=self.input_guard,
            session=session, speed=self.speed_ref, start_ms=self.start_ms,
            loop_range=self.loop_range, preview=self.preview,
        )
        worker.setProperty("playbackSession", session)
        thread.setProperty("playbackSession", session)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.prepared.connect(self.timeline_ready)
        worker.countdown.connect(self.countdown_changed)
        worker.playback_started.connect(self._playback_started)
        worker.progress.connect(self._playback_progress)
        worker.keys_pressed.connect(self._keys_pressed)
        worker.completed.connect(self._capture_result)
        worker.failed.connect(self._capture_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        thread.start()
        return True

    def set_input_guard(self, guard: Callable[[], bool] | None) -> None:
        """Set the safety guard captured by the next playback worker."""
        self.input_guard = guard

    @Slot(bool)
    def _capture_result(self, value: bool) -> None:
        self._result = value

    @Slot(str)
    def _capture_error(self, message: str) -> None:
        self._failure = message
        self.error.emit(message)

    @Slot()
    def _thread_finished(self) -> None:
        sender = self.sender()
        session = sender.property("playbackSession") if sender is not None else None
        if session is not None and int(session) != self._active_session:
            return
        result, failure = self._result, self._failure
        self._set_state("error" if failure else "idle")
        self.finished.emit(result)

    @Slot(int)
    def _playback_started(self, session: int) -> None:
        self._apply_playback_started(session)

    def _apply_playback_started(self, session: int) -> None:
        if session != self._active_session:
            return
        self._playback_has_started = True
        if self.current_song is not None:
            self.playback_started.emit(self.current_song)
        if self._stop.is_set() or self.state in {"stopping", "focus_paused"}:
            return
        self._set_state("playing")

    @Slot(int, int)
    def _playback_progress(self, session: int, elapsed: int) -> None:
        if session == self._active_session:
            self.progress_changed.emit(elapsed)

    @Slot(int, list)
    def _keys_pressed(self, session: int, keys: list) -> None:
        if session == self._active_session:
            self.keys_pressed.emit(keys)

    def toggle_pause(self) -> None:
        if self.state == "playing":
            self._pause.set()
            self._set_state("paused")
        elif self.state == "paused":
            self._pause.clear()
            self._set_state("playing")

    def pause_for_focus(self) -> bool:
        """Pause without confusing focus loss with a user's manual pause."""
        if self.state not in {"countdown", "starting", "playing"}:
            return False
        self._state_before_focus_pause = self.state
        self._pause.set()
        self._set_state("focus_paused")
        return True

    def resume_for_focus(self) -> bool:
        if self.state != "focus_paused":
            return False
        target_state = (
            "playing" if self._playback_has_started
            else self._state_before_focus_pause
        )
        self._pause.clear()
        self._set_state(target_state)
        return True

    def stop(self) -> None:
        if self.busy:
            self._stop.set()
            self._pause.clear()
            self._set_state("stopping")

    def _set_state(self, value: str) -> None:
        self.state = value
        self.state_changed.emit(value)
