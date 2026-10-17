"""Production integration layer for the Sky Instrument Console.

This module binds the visual prototype to validated repositories, persistent
settings, global hotkeys, and an explicit playback lifecycle.
"""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import (
    QObject, QPointF, QRectF, QSignalBlocker, Qt, QThread, QTimer, Signal, Slot,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget
from pynput import keyboard

from macro_core import MacroPlayer
from macro_player.domain import FavoriteEntry, Settings
from macro_player.repositories import (
    FavoritesRepository, RepositoryError, SettingsRepository, SheetRepository,
)
from sky_ui_core import FAVORITES_FILE, SHEETS_DIR, USER_DATA_DIR, NoteRunway, Song, Tokens
from sky_ui_window import MainWindow as PrototypeWindow


SETTINGS_FILE = USER_DATA_DIR / "hotkeys.json"


class RepositoryFavoritesStore:
    def __init__(self, path: Path = FAVORITES_FILE, sheets_dir: Path = SHEETS_DIR) -> None:
        self._repository = FavoritesRepository(path, sheets_dir)

    def load(self) -> set[str]:
        return {f"sheets\\{entry.path.replace('/', chr(92))}" for entry in self._repository.load()}

    def save(self, paths: Iterable[str]) -> None:
        self._repository.save(paths)

    def recover(self, paths: Iterable[str]):
        return self._repository.recover(paths)


class RepositorySheetLibrary:
    """UI-shaped adapter over the validated sheet and favorites repositories."""

    def __init__(self, sheets_dir: Path = SHEETS_DIR) -> None:
        self.sheets_dir = sheets_dir
        self.sheet_repository = SheetRepository(sheets_dir)
        self.favorites = RepositoryFavoritesStore(FAVORITES_FILE, sheets_dir)
        self.favorites_error: str | None = None
        self.compatibility = {}

    def songs(self) -> list[Song]:
        try:
            favorites = {
                entry.path.casefold() for entry in FavoritesRepository(
                    FAVORITES_FILE, self.sheets_dir
                ).load()
            }
        except RepositoryError as exc:
            favorites = set()
            self.favorites_error = str(exc)

        songs = []
        for relative in self.sheet_repository.list():
            audits = {
                layout: self.sheet_repository.audit(
                    relative, detail["json_map"].keys()
                )
                for layout, detail in MacroPlayer.KEY_LAYOUTS.items()
            }
            self.compatibility[relative.casefold()] = audits
            try:
                title = self.sheet_repository.load(relative).title
            except RepositoryError:
                title = Path(relative).stem
            if not all(audit.playable for audit in audits.values()):
                title += " · Không hỗ trợ"
            songs.append(Song(
                self.sheet_repository.root / relative,
                title,
                relative.casefold() in favorites,
            ))
        return songs

    def relative_id(self, path: Path) -> str:
        return path.resolve().relative_to(self.sheet_repository.root).as_posix()

    def compatibility_error(self, path: Path, layout: str) -> str | None:
        try:
            relative = self.relative_id(path)
        except ValueError:
            return None
        detail = MacroPlayer.KEY_LAYOUTS.get(layout)
        if detail is None:
            return f"Không tìm thấy bộ phím '{layout}'."
        audit = self.sheet_repository.audit(relative, detail["json_map"].keys())
        self.compatibility.setdefault(relative.casefold(), {})[layout] = audit
        if audit.error:
            return audit.error
        if audit.unsupported_keys:
            keys = ", ".join(audit.unsupported_keys)
            return f"Sheet dùng phím chưa hỗ trợ: {keys}."
        return None


def load_validated_sheet(path: Path):
    repository = SheetRepository(path.parent)
    sheet = repository.load(path.name)
    moments = sorted({int(note.time) for note in sheet.notes})
    # MacroPlayer consumes the legacy representation. Expand chord lists into
    # simultaneous note records so validation stays centralized.
    payload = {
        "name": sheet.title,
        "songNotes": [
            {"time": note.time, "key": key}
            for note in sheet.notes
            for key in note.keys
        ],
    }
    return payload, moments, moments[-1] if moments else 0


class PlaybackWorker(QObject):
    prepared = Signal(list, int)
    countdown = Signal(int)
    playback_started = Signal(int)
    progress = Signal(int, int)
    completed = Signal(bool)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, song: Song, layout: str, stop: threading.Event,
                 pause: threading.Event, countdown: int,
                 input_guard: Callable[[], bool] | None = None,
                 session: int = 0) -> None:
        super().__init__()
        self.song, self.layout = song, layout
        self.stop, self.pause, self.countdown_seconds = stop, pause, countdown
        self.input_guard = input_guard
        self.session = session

    def _input_allowed(self) -> bool:
        if self.input_guard is None:
            return True
        try:
            return bool(self.input_guard())
        except Exception:
            return False

    @Slot()
    def run(self) -> None:
        try:
            data, moments, duration = load_validated_sheet(self.song.path)
            self.prepared.emit(moments, duration)
            remaining_time = float(self.countdown_seconds)
            last_tick = time.monotonic()
            last_displayed = None
            while remaining_time > 0:
                if self.stop.is_set():
                    self.completed.emit(False)
                    return
                now = time.monotonic()
                if self.pause.is_set() or not self._input_allowed():
                    last_tick = now
                    self.stop.wait(0.05)
                    continue
                remaining_time = max(0.0, remaining_time - (now - last_tick))
                last_tick = now
                displayed = max(1, int(remaining_time + 0.999))
                if displayed != last_displayed:
                    self.countdown.emit(displayed)
                    last_displayed = displayed
                self.stop.wait(min(0.05, remaining_time))
            if self.stop.is_set():
                self.completed.emit(False)
                return
            self.playback_started.emit(self.session)
            player = MacroPlayer(
                input_guard=self.input_guard,
                progress_callback=lambda elapsed: self.progress.emit(
                    self.session, int(elapsed)
                ),
            )
            player.set_key_layout(self.layout)
            completed = bool(player.play_json_sheet(data, self.stop, self.pause, 0))
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
    error = Signal(str)
    finished = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = None
        self._worker = None
        self._stop, self._pause = threading.Event(), threading.Event()
        self._result, self._failure = False, None
        self._state_before_focus_pause = "playing"
        self._session_counter = self._active_session = 0
        self._playback_has_started = False
        self.input_guard: Callable[[], bool] | None = None
        self.state, self.current_song = "idle", None
        self.layout_name, self.countdown = "old", 3

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
            song, self.layout_name, self._stop, self._pause, self.countdown,
            self.input_guard, session,
        )
        worker.setProperty("playbackSession", session)
        thread.setProperty("playbackSession", session)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.prepared.connect(self.timeline_ready)
        worker.countdown.connect(self.countdown_changed)
        worker.playback_started.connect(self._playback_started)
        worker.progress.connect(self._playback_progress)
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
        if self._stop.is_set() or self.state in {"stopping", "focus_paused"}:
            return
        self._set_state("playing")

    @Slot(int, int)
    def _playback_progress(self, session: int, elapsed: int) -> None:
        if session == self._active_session:
            self.progress_changed.emit(elapsed)

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


def canonical_hotkey(value: str) -> str:
    aliases = {
        "escape": "esc", "control": "ctrl", "ctl": "ctrl",
        "return": "enter", "windows": "cmd", "win": "cmd",
        "super": "cmd", "option": "alt",
    }
    parts = [aliases.get(part.strip().casefold(), part.strip().casefold())
             for part in value.split("+") if part.strip()]
    modifiers = ("ctrl", "alt", "shift", "cmd")
    ordered = [item for item in modifiers if item in parts]
    ordered.extend(item for item in parts if item not in modifiers)
    special = {
        *modifiers, "esc", "enter", "space", "tab", "delete", "backspace",
        "left", "right", "up", "down", "home", "end", "page_up", "page_down",
        *(f"f{i}" for i in range(1, 25)),
    }
    return "+".join(f"<{part}>" if part in special else part for part in ordered)


class GlobalHotkeyService(QObject):
    pause_requested, stop_requested, next_requested = Signal(), Signal(), Signal()
    slot_requested = Signal(int)
    error = Signal(str)

    RESERVED = {"<ctrl>+<alt>+<delete>", "<cmd>+l"}

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener = None
        self._settings: Settings | None = None
        self._listener_watch = QTimer(self)
        self._listener_watch.setInterval(500)
        self._listener_watch.timeout.connect(self._check_listener)

    def _bindings(self, settings: Settings) -> dict[str, Callable[[], None]]:
        raw: list[tuple[str, Callable[[], None]]] = [
            (settings.pause_hotkey, self.pause_requested.emit),
            (settings.hotkeys.get("stop", "esc"), self.stop_requested.emit),
            (settings.hotkeys.get("next", "f10"), self.next_requested.emit),
        ]
        raw.extend((key, lambda index=index: self.slot_requested.emit(index))
                   for index, key in enumerate(settings.hotkey_keys))
        bindings = [(canonical_hotkey(key), callback) for key, callback in raw if key.strip()]
        keys = [key for key, _ in bindings]
        if len(keys) != len(set(keys)):
            raise ValueError("Global hotkeys bị trùng; cấu hình đang dùng được giữ nguyên.")
        if any(key in self.RESERVED for key in keys):
            raise ValueError("Một global hotkey được Windows giữ riêng; cấu hình đang dùng được giữ nguyên.")
        for key in keys:
            keyboard.HotKey.parse(key)
        return dict(bindings)

    def start(self, settings: Settings) -> bool:
        try:
            candidate = keyboard.GlobalHotKeys(self._bindings(settings))
        except Exception as exc:
            self.error.emit(f"Không thể áp dụng global hotkeys: {exc}")
            return False

        previous_settings = self._settings
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        try:
            candidate.start()
            wait_until_ready = getattr(candidate, "wait", None)
            if callable(wait_until_ready):
                wait_until_ready()
            join = getattr(candidate, "join", None)
            if callable(join):
                join(0.05)
            is_alive = getattr(candidate, "is_alive", None)
            if callable(is_alive) and not is_alive():
                raise OSError("listener đã dừng trong lúc khởi tạo hook")
        except Exception as exc:
            try:
                candidate.stop()
            except Exception:
                pass
            if previous_settings is not None:
                try:
                    rollback = keyboard.GlobalHotKeys(self._bindings(previous_settings))
                    rollback.start()
                    self._listener = rollback
                except Exception as rollback_exc:
                    self.error.emit(
                        f"Không thể bật global hotkeys mới ({exc}); "
                        f"khôi phục cấu hình cũ cũng thất bại ({rollback_exc})."
                    )
                    return False
            suffix = (
                "Cấu hình cũ đã được khôi phục."
                if previous_settings is not None
                else "Chưa có listener nào được bật."
            )
            self.error.emit(f"Không thể bật global hotkeys mới: {exc}. {suffix}")
            return False
        self._listener = candidate
        self._settings = settings
        self._listener_watch.start()
        return True

    def _check_listener(self) -> None:
        listener = self._listener
        is_alive = getattr(listener, "is_alive", None) if listener is not None else None
        if callable(is_alive) and not is_alive():
            self._listener = None
            self._listener_watch.stop()
            self.error.emit(
                "Global hotkeys đã dừng ngoài dự kiến. Dùng nút Dừng trong ứng dụng "
                "và mở lại ứng dụng để khôi phục hook."
            )

    def stop(self) -> None:
        self._listener_watch.stop()
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


class StaffNoteRunway(NoteRunway):
    """Five staff lines make the runway unmistakably musical without ornament."""

    def paintEvent(self, event) -> None:
        self._sync_elapsed()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(8, 8, -8, -8)
        gradient = QLinearGradient(bounds.topLeft(), bounds.topRight())
        gradient.setColorAt(0, QColor(Tokens.DEEP_SLATE))
        gradient.setColorAt(1, QColor("#1D3045"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(bounds), 10, 10)
        center = bounds.center().y()
        painter.setPen(QPen(QColor(Tokens.BORDER), 1))
        for offset in (-16, -8, 0, 8, 16):
            painter.drawLine(bounds.left() + 12, int(center + offset),
                             bounds.right() - 12, int(center + offset))
        progress = self._elapsed / self._duration
        playhead = bounds.left() + bounds.width() * .26
        painter.setPen(QPen(QColor(Tokens.APRICOT), 2))
        painter.drawLine(int(playhead), bounds.top() + 7, int(playhead), bounds.bottom() - 7)
        painter.setPen(Qt.PenStyle.NoPen)
        for index, moment in enumerate(self._moments):
            x = playhead + (moment / self._duration - progress) * bounds.width() * .72
            if bounds.left() + 8 <= x <= bounds.right() - 8:
                color = QColor(Tokens.SKY_BLUE)
                color.setAlphaF(max(.2, 1 - abs(x-playhead)/max(1, bounds.width())*1.8))
                painter.setBrush(color)
                painter.drawEllipse(QPointF(x, center + ((index % 5)-2)*8), 3.2, 3.2)


class HotkeySummaryPage(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        title = QLabel("Phím tắt")
        title.setObjectName("pageTitle")
        copy = QLabel("Global hotkeys đang dùng cấu hình đã lưu trong hotkeys.json.")
        copy.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(copy)
        layout.addSpacing(16)
        rows = [
            ("Tạm dừng / tiếp tục", settings.pause_hotkey),
            ("Dừng", settings.hotkeys.get("stop", "Esc")),
            ("Bài tiếp theo", settings.hotkeys.get("next", "F10")),
        ]
        rows.extend((f"Phát ô {index + 1}", key)
                    for index, key in enumerate(settings.hotkey_keys))
        for label, key in rows:
            line = QLabel(f"{label}:  {key}")
            line.setMinimumHeight(32)
            layout.addWidget(line)
        layout.addStretch(1)


class MainWindow(PrototypeWindow):
    def __init__(self, *,
                 hotkey_service: GlobalHotkeyService | None = None) -> None:
        self.settings_repository = SettingsRepository(SETTINGS_FILE)
        self.settings_error = None
        try:
            self.settings = self.settings_repository.load()
        except RepositoryError as exc:
            self.settings, self.settings_error = Settings(), str(exc)
        controller = PlaybackController()
        super().__init__(RepositorySheetLibrary(), controller=controller)

        self.controller.layout_name = self.settings.keyboard_layout
        self.controller.countdown = self.settings.countdown_seconds
        self.controller.countdown_changed.connect(self._countdown_status)
        self.controller.progress_changed.connect(self._progress_status)

        self._install_integrated_copy()
        self._replace_runway()
        self._replace_hotkeys_page()
        self._apply_settings()
        self.settings_page.reduced_motion_changed.connect(self._set_reduced_motion)
        self.hotkeys = hotkey_service or GlobalHotkeyService(self)
        self.hotkeys.pause_requested.connect(self.controller.toggle_pause)
        self.hotkeys.stop_requested.connect(self.stop_playback)
        self.hotkeys.next_requested.connect(self.play_next)
        self.hotkeys.slot_requested.connect(self._play_slot)
        self.hotkeys.error.connect(self._show_error)
        self.hotkeys.start(self.settings)
        if getattr(self.library_source, "favorites_error", None):
            self._show_error(
                "Không thể đọc danh sách yêu thích; thư viện vẫn được mở. "
                + self.library_source.favorites_error
            )
        if self.settings_error:
            self._show_error(self.settings_error)

    def _install_integrated_copy(self) -> None:
        for button in [*self.findChildren(QPushButton), *self.mini.findChildren(QPushButton)]:
            button.setMinimumHeight(36)
        for button in self.mini.findChildren(QPushButton):
            button.setMinimumHeight(44)
        self.queue.hint.setText("Hàng chờ đang trống. Chọn một bài trong thư viện và nhấn “Thêm hàng chờ”.")

    def _replace_runway(self) -> None:
        old = self.dock.runway
        runway = StaffNoteRunway()
        self.dock.layout().replaceWidget(old, runway)
        old.hide()
        old.deleteLater()
        self.dock.runway = runway
        self.settings_page.reduced_motion_changed.connect(runway.set_reduced_motion)

    def _replace_hotkeys_page(self) -> None:
        old = self.hotkeys_page
        page = HotkeySummaryPage(self.settings)
        self.pages.removeWidget(old)
        self.pages.insertWidget(1, page)
        self.hotkeys_page = page
        old.deleteLater()

    def _apply_settings(self) -> None:
        self.settings_page.countdown.setMaximum(30)
        blockers = [
            QSignalBlocker(self.settings_page.key_layout),
            QSignalBlocker(self.settings_page.countdown),
            QSignalBlocker(self.settings_page.always_on_top),
            QSignalBlocker(self.settings_page.reduced_motion),
        ]
        try:
            index = self.settings_page.key_layout.findData(self.settings.keyboard_layout)
            self.settings_page.key_layout.setCurrentIndex(max(0, index))
            self.settings_page.countdown.setValue(self.settings.countdown_seconds)
            self.settings_page.countdown_value.setText(
                f"{self.settings.countdown_seconds} giây"
            )
            self.settings_page.always_on_top.setChecked(self.settings.always_on_top)
            self.settings_page.reduced_motion.setChecked(self.settings.reduced_motion)
        finally:
            del blockers
        super()._set_layout(self.settings.keyboard_layout)
        super()._set_countdown(self.settings.countdown_seconds)
        super()._set_mini_on_top(self.settings.always_on_top)
        self.dock.runway.set_reduced_motion(self.settings.reduced_motion)
        self.setWindowOpacity(self.settings.window_opacity)

    def _save_settings(self, **changes) -> bool:
        updated = replace(self.settings, **changes)
        try:
            if self.settings_error:
                backup = self.settings_repository.recover(updated)
                self.settings_error = None
                if backup is not None:
                    self.dock.status.setText(
                        f"Đã sao lưu cấu hình lỗi tại {backup.name} và lưu cấu hình mới."
                    )
            else:
                self.settings_repository.save(updated)
        except RepositoryError as exc:
            self._show_error(str(exc))
            return False
        self.settings = updated
        return True

    def _set_layout(self, value: str) -> None:
        if self._save_settings(keyboard_layout=value):
            super()._set_layout(value)
        else:
            self._apply_settings()

    def _set_countdown(self, value: int) -> None:
        if self._save_settings(countdown_seconds=value):
            super()._set_countdown(value)
        else:
            self._apply_settings()

    def _set_mini_on_top(self, value: bool) -> None:
        if self._save_settings(always_on_top=value):
            super()._set_mini_on_top(value)
        else:
            self._apply_settings()

    def _set_reduced_motion(self, value: bool) -> None:
        if not self._save_settings(reduced_motion=value):
            self._apply_settings()

    @Slot(object)
    def play_song(self, song: Song) -> bool:
        checker = getattr(self.library_source, "compatibility_error", None)
        error = checker(song.path, self.controller.layout_name) if checker else None
        if error:
            self._show_error(f"Bài “{song.title}” chưa thể phát: {error}")
            return False
        return super().play_song(song)

    @Slot(int)
    def _progress_status(self, elapsed: int) -> None:
        self.dock.runway.set_progress(elapsed)
        self.mini.set_progress(elapsed, self.dock.runway._duration)

    @Slot(object)
    def toggle_favorite(self, song: Song) -> None:
        updated = [
            Song(item.path, item.title, not item.favorite) if item.path == song.path else item
            for item in self.songs
        ]
        try:
            favorites = [item.identity for item in updated if item.favorite]
            if getattr(self.library_source, "favorites_error", None):
                backup = self.library_source.favorites.recover(favorites)
                self.library_source.favorites_error = None
                if backup is not None:
                    self.dock.status.setText(
                        f"Đã sao lưu yêu thích lỗi tại {backup.name} và lưu danh sách mới."
                    )
            else:
                self.library_source.favorites.save(favorites)
        except RepositoryError as exc:
            self._show_error(f"Không thể lưu danh sách yêu thích: {exc}")
            return
        self.songs = updated
        self.library_page.songs = updated
        self.library_page.rebuild()

    @Slot(int)
    def _countdown_status(self, remaining: int) -> None:
        self.dock.status.setStyleSheet("")
        self.dock.status.setText(f"Bắt đầu sau {remaining} giây")

    @Slot(str)
    def _state_changed(self, state: str) -> None:
        if state == "error":
            self.dock.runway.set_playing(False)
            self.mini.sync(self.current_song, state)
        elif state in {"countdown", "starting"}:
            self.dock.runway.set_playing(False)
            self.mini.sync(self.current_song, state)
            self.dock.status.setText("Đang chuẩn bị")
        else:
            super()._state_changed(state)

    @Slot(int)
    def _play_slot(self, index: int) -> None:
        if self._closing:
            return
        if index >= len(self.settings.song_slots):
            return
        selected = self.settings.song_slots[index]
        if not selected:
            return
        normalized = selected.replace(chr(92), "/").casefold()
        exact = [
            item for item in self.songs
            if self.library_source.relative_id(item.path).casefold() == normalized
        ]
        matches = exact
        if not matches and "/" not in normalized:
            matches = [
                item for item in self.songs
                if item.path.name.casefold() == normalized
            ]
        song = matches[0] if len(matches) == 1 else None
        if song:
            self.play_song(song)
        elif len(matches) > 1:
            self._show_error(
                f"Tên bài cũ bị trùng cho phím {index + 1}: {selected}. "
                "Hãy gán lại bài bằng đường dẫn đầy đủ."
            )
        else:
            self._show_error(f"Không tìm thấy bài đã gán cho phím {index + 1}: {selected}")

    def closeEvent(self, event) -> None:
        self.hotkeys.stop()
        super().closeEvent(event)
