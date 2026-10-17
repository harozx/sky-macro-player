"""The one main window: composes pages and widgets, owns the command flow.

Widgets only display state and emit intents. Every playback command goes
through this window so Stop, shutdown and scheduled commands share one path.
"""

from __future__ import annotations

import random
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping

from PySide6.QtCore import QFileSystemWatcher, QSignalBlocker, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, batch, paths
from ..diagnostics import build_report
from ..domain import HistoryEntry, LibraryState, Settings, SongPreference
from ..engine import MacroPlayer
from ..hotkeys import (
    DefaultHotkeyService,
    DisabledHotkeyService,
    GlobalHotkeyService,
    with_legacy_defaults,
)
from ..i18n import set_language, tr
from ..library import ImportRecord, Library, Song, path_fingerprint
from ..playback import PlaybackController, load_song_events
from ..repositories import LibraryStateRepository, RepositoryError, SettingsRepository
from ..sheet_tools import save_new_sheet, to_sheet_payload
from ..updates import UpdateChecker
from ..window_focus import (
    FocusService,
    WindowInfo,
    WindowsFocusService,
    pickable_windows,
)
from .dialogs import CommandPalette, ImportDialog, OnboardingWizard, WindowPickerDialog
from .dock import PlaybackDock
from .hotkeys_page import EditableHotkeysPage
from .library_page import LibraryPage
from .mini import STATE_LABELS, MiniOverlay
from .queue_panel import QueuePanel
from .settings_page import SettingsPage
from .sheet_editor import SheetEditorDialog
from .sound import PreviewSynth
from .text_import import BatchDialog, TextSheetDialog
from .theme import STYLE
from .tray import TrayController, app_icon
from .widgets import KeyGrid, format_duration

SHEET_SUFFIXES = {".txt", ".json"}


class MainWindow(QMainWindow):
    closed = Signal()

    def __init__(self, *, enable_global_hotkeys: bool = True,
                 hotkey_service: GlobalHotkeyService | None = None,
                 focus_service: FocusService | None = None,
                 library: Library | None = None,
                 controller: PlaybackController | None = None,
                 show_onboarding: bool = False,
                 use_tray: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Sky Macro Player")
        self.setWindowIcon(app_icon())
        # 960×540 is the logical size of a 1080p screen at 200% scaling.
        self.setMinimumSize(760, 520)
        self.resize(1240, 800)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)

        self.settings_repository = SettingsRepository(paths.settings_file())
        self.settings_error: str | None = None
        try:
            self.settings = self.settings_repository.load()
        except RepositoryError as exc:
            self.settings, self.settings_error = Settings(), str(exc)
        # Chosen before any widget exists; changing it takes effect on restart.
        set_language(self.settings.language)
        self.state_repository = LibraryStateRepository(paths.library_state_file())
        self.state_error: str | None = None
        try:
            self.library_state = self.state_repository.load()
        except RepositoryError as exc:
            self.library_state, self.state_error = LibraryState(), str(exc)
        if library is None:
            try:
                paths.seed_user_sheets()
            except OSError as exc:
                self.settings_error = self.settings_error or tr(
                    "Không thể chép sheet mẫu: {exc}").format(exc=exc)
            library = Library(paths.user_sheets_dir(), paths.favorites_file())
        self.library = library
        self.controller = controller or PlaybackController(self)
        if self.controller.parent() is None:
            self.controller.setParent(self)
        self.focus_service = focus_service or WindowsFocusService(self.settings.focus_target_exe)

        self.current_song: Song | None = None
        self.pending_song: Song | None = None
        self._closing = False
        self._quitting = False
        self.close_pending = False
        self._command_generation = 0
        self._rng = random.Random()
        self.sky_window: WindowInfo | None = None
        self.active_sky_window: WindowInfo | None = None
        self.focus_paused = False
        self.preview_mode = False
        self._session_preview = False
        self._session_from_queue = False
        self.cursor: tuple[str, int] | None = None  # type: ignore[assignment]
        self._preview_override: tuple[Song, tuple] | None = None
        self._restore_countdown: int | None = None
        self.sheet_editor: SheetEditorDialog | TextSheetDialog | None = None
        self._last_import: list = []
        self._last_play_failure: str | None = None
        self.loop_marks: dict[str, Any] = {"song": None, "a": None, "b": None}
        self._mini_position = self.settings.mini_position
        self._tray_hint_shown = False
        self._wide_layout: bool | None = None

        self.songs = self._scan_songs()
        self._build_ui()
        self._connect()
        self._install_shortcuts()
        self._apply_settings()

        self.hotkeys = hotkey_service or (
            DefaultHotkeyService(self) if enable_global_hotkeys else DisabledHotkeyService(self))
        if self.hotkeys.parent() is None:
            self.hotkeys.setParent(self)
        self.hotkeys.pause_requested.connect(self.toggle_play)
        self.hotkeys.stop_requested.connect(self.stop_playback)
        self.hotkeys.next_requested.connect(self.play_next)
        self.hotkeys.slot_requested.connect(self._play_slot)
        self.hotkeys.error.connect(self._show_error)
        self.hotkeys.start(self.settings)

        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(250)
        self.focus_timer.timeout.connect(self._poll_focus_lock)
        self.focus_timer.start()

        self.synth = PreviewSynth(paths.user_data_dir() / "cache" / "tones", self)
        self.tray = TrayController(self) if use_tray and TrayController.available() else None
        if self.tray is not None:
            self.tray.show_requested.connect(self._show_from_tray)
            self.tray.play_requested.connect(self.toggle_play)
            self.tray.next_requested.connect(self.play_next)
            self.tray.stop_requested.connect(self.stop_playback)
            self.tray.mini_requested.connect(self.toggle_mini)
            self.tray.quit_requested.connect(self.quit_app)
            self.tray.show()

        self.watcher = QFileSystemWatcher(self)
        self._watch_library()
        self.watcher.directoryChanged.connect(lambda _: self._refresh_timer.start())
        self.watcher.fileChanged.connect(lambda _: self._refresh_timer.start())
        self._refresh_timer: QTimer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(600)
        self._refresh_timer.timeout.connect(self.refresh_library)

        if self.songs:
            self.library_page.list.setCurrentRow(0)
        if self.library.favorites_error:
            self._show_error(tr("Không thể đọc danh sách yêu thích; thư viện vẫn được mở. ")
                             + self.library.favorites_error)
        if self.state_error:
            self._show_error(tr("Không đọc được lịch sử nghe; dữ liệu cũ được giữ nguyên. "
                             "{state_error}").format(state_error=self.state_error))
        if self.settings_error:
            self._show_error(self.settings_error)
        self.updates = UpdateChecker(self)
        self.updates.update_available.connect(self._update_available)
        self.updates.up_to_date.connect(
            lambda: self.dock.set_status(tr("Đang dùng bản mới nhất ({__version__}).").format(
                __version__=__version__), "success"))
        self.updates.failed.connect(
            lambda message: self.dock.set_status(
                tr("Không kiểm tra được cập nhật: {message}").format(message=message)))
        if show_onboarding and not self.settings.first_run_completed:
            QTimer.singleShot(300, self.run_onboarding)
        if show_onboarding and self.settings.check_updates:
            QTimer.singleShot(2000, self.updates.check)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.mini = MiniOverlay()
        self.mini.setWindowIcon(app_icon())
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        shell = QVBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        shell.addLayout(content, 1)

        self.rail = QWidget()
        self.rail.setObjectName("rail")
        self.rail.setFixedWidth(178)
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(16, 20, 16, 18)
        brand = QLabel("Sky Macro")
        brand.setObjectName("brand")
        tagline = QLabel("INSTRUMENT CONSOLE")
        tagline.setObjectName("eyebrow")
        rail_layout.addWidget(brand)
        rail_layout.addWidget(tagline)
        rail_layout.addSpacing(28)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.pages = QStackedWidget()
        self.library_page = LibraryPage(self.songs)
        self.library_page.policies = self._policies()
        self.hotkeys_page = EditableHotkeysPage(self.settings, self.songs)
        self.settings_page = SettingsPage()
        for page in (self.library_page, self.hotkeys_page, self.settings_page):
            self.pages.addWidget(page)
        self.nav_buttons = []
        for index, label in enumerate((tr("Thư viện"), tr("Phím tắt"), tr("Cài đặt"))):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.setAccessibleName(tr("Mở {label}").format(label=label))
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, page=index: self.show_page(page))
            self.nav_group.addButton(button)
            self.nav_buttons.append(button)
            rail_layout.addWidget(button)
        self.queue_toggle = QPushButton(tr("Hàng chờ"))
        self.queue_toggle.setCheckable(True)
        self.queue_toggle.setChecked(True)
        self.queue_toggle.setAccessibleName(tr("Hiện hoặc ẩn hàng chờ"))
        rail_layout.addWidget(self.queue_toggle)
        palette = QPushButton(tr("Bảng lệnh"))
        palette.setToolTip(tr("Ctrl+K: tìm bài và chạy lệnh nhanh"))
        palette.clicked.connect(self.open_command_palette)
        rail_layout.addWidget(palette)
        rail_layout.addStretch(1)
        version = QLabel(tr("PHIÊN BẢN {__version__}").format(__version__=__version__))
        version.setObjectName("eyebrow")
        rail_layout.addWidget(version)
        content.addWidget(self.rail)
        content.addWidget(self.pages, 1)
        self.queue = QueuePanel()
        self.queue.set_playlists(sorted(self.library_state.playlists))
        content.addWidget(self.queue)
        self.queue_toggle.setText(tr("Ẩn hàng chờ"))

        self.key_strip = QFrame()
        self.key_strip.setObjectName("keyStrip")
        strip_layout = QHBoxLayout(self.key_strip)
        strip_layout.setContentsMargins(22, 4, 22, 4)
        self.key_strip_label = QLabel(tr("Bàn phím"))
        self.key_strip_label.setObjectName("eyebrow")
        self.key_grid = KeyGrid()
        strip_layout.addWidget(self.key_strip_label)
        strip_layout.addStretch(1)
        strip_layout.addWidget(self.key_grid)
        strip_layout.addStretch(1)
        self.key_strip.hide()
        shell.addWidget(self.key_strip)
        self.dock = PlaybackDock()
        shell.addWidget(self.dock)
        self.settings_page.version_label.setText(
            tr("Phiên bản {__version__} · Dữ liệu: {0}").format(
                paths.user_data_dir(), __version__=__version__))

    def _connect(self) -> None:
        page = self.library_page
        page.play_requested.connect(self.play_song)
        page.queue_requested.connect(self.add_to_queue)
        page.favorite_requested.connect(self.toggle_favorite)
        page.play_all_requested.connect(self.play_all)
        page.import_requested.connect(self.choose_import_files)
        page.layer_policy_changed.connect(self.set_layer_policy)
        page.edit_requested.connect(self.open_sheet_editor)
        page.undo_import_requested.connect(self.undo_last_import)
        page.text_import_requested.connect(self.open_text_import)
        page.batch_requested.connect(self.choose_batch_folder)
        page.list.currentItemChanged.connect(lambda *_: self._selection_changed())
        self.queue.play_requested.connect(self._play_queued_song)
        self.queue.save_playlist_requested.connect(self.save_playlist)
        self.queue.load_playlist_requested.connect(self.load_playlist)
        self.queue.delete_playlist_requested.connect(self.delete_playlist)
        self.queue_toggle.toggled.connect(self._set_queue_visible)
        dock = self.dock
        dock.play_requested.connect(self.toggle_play)
        dock.next_requested.connect(self.play_next)
        dock.stop_requested.connect(self.stop_playback)
        dock.mini_requested.connect(self.toggle_mini)
        dock.speed_changed.connect(self.set_speed)
        dock.set_a_requested.connect(lambda: self.set_loop_mark("a"))
        dock.set_b_requested.connect(lambda: self.set_loop_mark("b"))
        dock.clear_loop_requested.connect(self.clear_loop)
        dock.preview_toggled.connect(self.set_preview_mode)
        dock.keyboard_toggled.connect(self.key_strip.setVisible)
        dock.runway.position_clicked.connect(self.set_cursor)
        mini = self.mini
        mini.play_requested.connect(self.toggle_play)
        mini.next_requested.connect(self.play_next)
        mini.stop_requested.connect(self.stop_playback)
        mini.expand_requested.connect(self._expand_from_mini)
        mini.pin_changed.connect(self.settings_page.always_on_top.setChecked)
        mini.position_changed.connect(lambda x, y: setattr(self, "_mini_position", (x, y)))
        controller = self.controller
        controller.song_changed.connect(self._song_changed)
        controller.state_changed.connect(self._state_changed)
        controller.timeline_ready.connect(self._timeline_ready)
        controller.countdown_changed.connect(self._countdown_status)
        controller.progress_changed.connect(self._progress_status)
        controller.keys_pressed.connect(self._keys_pressed)
        controller.playback_started.connect(self._record_play)
        controller.error.connect(lambda message: self._show_error(
            tr("Lỗi phát nhạc: {message}").format(message=message)))
        controller.finished.connect(self._playback_finished)
        controller.loader = self._load_for_playback
        sp = self.settings_page
        sp.reduced_motion_changed.connect(self._set_reduced_motion)
        sp.layout_changed.connect(self._set_layout)
        sp.custom_layout_saved.connect(self._save_custom_layout)
        sp.countdown_changed.connect(self._set_countdown)
        sp.always_on_top.toggled.connect(self._set_mini_on_top)
        sp.minimize_to_tray_changed.connect(
            lambda value: self._save_or_restore(minimize_to_tray=value))
        sp.preview_sound_changed.connect(
            lambda value: self._save_or_restore(preview_sound=value))
        sp.focus_lock_checkbox.toggled.connect(self._set_focus_lock)
        sp.resume_focus_checkbox.toggled.connect(self._set_resume_on_focus)
        sp.test_window_requested.connect(lambda: self.dock.set_status(*self._test_window()))
        sp.pick_target_requested.connect(self.pick_target_window)
        sp.reset_target_requested.connect(lambda: self._set_target_exe(None))
        sp.diagnostics_requested.connect(self.export_diagnostics)
        sp.onboarding_requested.connect(self.run_onboarding)
        sp.check_updates_changed.connect(
            lambda value: self._save_or_restore(check_updates=value))
        sp.language_changed.connect(self._set_language)
        sp.check_now_requested.connect(lambda: self.updates.check())
        sp.open_data_requested.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.user_data_dir()))))
        self.hotkeys_page.save_requested.connect(self._save_hotkeys)

    def _install_shortcuts(self) -> None:
        for shortcut, handler, protect_text_input in (
            ("Space", self.toggle_play, True),
            ("Escape", self.stop_playback, False),
            ("Ctrl+Right", self.play_next, True),
            ("Ctrl+M", self.toggle_mini, False),
            ("Ctrl+F", self.focus_search, False),
            ("Ctrl+K", self.open_command_palette, False),
            ("Ctrl+O", self.choose_import_files, False),
        ):
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            if protect_text_input:
                action.triggered.connect(
                    lambda checked=False, callback=handler: self._run_unless_editing(callback))
            else:
                action.triggered.connect(lambda checked=False, callback=handler: callback())
            self.addAction(action)

    def _run_unless_editing(self, callback) -> None:
        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QComboBox)):
            return
        callback()

    def show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def focus_search(self) -> None:
        self.show_page(0)
        self.library_page.search.setFocus()
        self.library_page.search.selectAll()

    def _set_queue_visible(self, visible: bool) -> None:
        self.queue.setVisible(visible)
        self.queue_toggle.setText(tr("Ẩn hàng chờ") if visible else tr("Hiện hàng chờ"))

    # ------------------------------------------------------------ library
    def _key_map(self) -> dict[str, str]:
        if self.settings.keyboard_layout == "custom" and self.settings.custom_layout_keys:
            return MacroPlayer.layout_map(self.settings.custom_layout_keys)
        layout = MacroPlayer.KEY_LAYOUTS.get(self.settings.keyboard_layout,
                                             MacroPlayer.KEY_LAYOUTS["old"])
        return dict(layout["json_map"])

    def _policies(self) -> dict[str, str | None]:
        return {path: pref.layer_policy for path, pref in self.library_state.preferences.items()
                if pref.layer_policy}

    def _scan_songs(self) -> list[Song]:
        last_played: dict[str, float] = {}
        for entry in self.library_state.history:
            last_played.setdefault(entry.path, entry.played_at)
        return self.library.scan(self._key_map().keys(), self._policies(),
                                 self.library_state.play_counts, last_played)

    def _watch_library(self) -> None:
        folders = [str(self.library.root)] + [
            str(path) for path in self.library.root.rglob("*") if path.is_dir()]
        existing = set(self.watcher.directories())
        missing = [folder for folder in folders if folder not in existing]
        if missing:
            self.watcher.addPaths(missing)

    @Slot()
    def refresh_library(self) -> None:
        self.songs = self._scan_songs()
        self.library_page.policies = self._policies()
        self.library_page.set_songs(self.songs)
        self.hotkeys_page.update_songs(self.songs)
        self._watch_library()

    def _song_for(self, identity: str) -> Song | None:
        folded = identity.replace("\\", "/").casefold()
        return next((song for song in self.songs if song.identity.casefold() == folded), None)

    def _relative_or_none(self, song: Song) -> str | None:
        if song.relative:
            return song.relative
        try:
            return self.library.relative_id(song.path)
        except (ValueError, OSError):
            return None

    def _compatibility_error(self, song: Song) -> str | None:
        relative = self._relative_or_none(song)
        if relative is None:
            return None
        try:
            self.library.prepare(relative, self._key_map().keys(), self._policies().get(relative))
        except RepositoryError as exc:
            return str(exc)
        return None

    def _load_for_playback(self, song: Song):
        override = self._preview_override
        if override is not None and override[0] is song:
            return override[1]
        relative = self._relative_or_none(song)
        if relative is None:
            return load_song_events(song)
        return self.library.prepare(relative, self._key_map().keys(),
                                    self._policies().get(relative))

    def _selection_changed(self) -> None:
        song = self.library_page.selected_song()
        if song is None or self.controller.busy:
            return
        relative = self._relative_or_none(song)
        if relative is None:
            return
        try:
            _, moments, duration = self.library.prepare(
                relative, self._key_map().keys(), self._policies().get(relative))
        except RepositoryError:
            moments, duration = [], 0
        runway = self.dock.runway
        runway.set_timeline(moments, duration)
        self._sync_markers(song)
        self.dock.title.setText(song.title)
        self.dock.title.setToolTip(song.title)
        if self.controller.state in {"idle", "error"}:
            self.dock.set_status(tr("Đã chọn · nhấn Phát hoặc bấm Note Runway để chọn vị trí"))
        prefs = self.library_state.preferences.get(song.identity)
        self.dock.set_speed(prefs.speed if prefs and prefs.speed else self.settings.speed)

    # ----------------------------------------------------------- playback
    @Slot(object)
    def play_song(self, song: Song) -> bool:
        self._last_play_failure = None
        if self._closing:
            self._last_play_failure = "closing"
            return False
        error = self._compatibility_error(song)
        if error:
            self._last_play_failure = "unplayable"
            self._show_error(tr("Bài “{title}” chưa thể phát: {error}").format(
                title=song.title, error=error))
            return False
        preview = self.preview_mode
        if not self.controller.busy:
            if self.settings.focus_lock_enabled and not preview:
                window = self._locate_sky_window()
                if window is None:
                    self._last_play_failure = "focus"
                    self._show_error(
                        tr("Không tìm thấy cửa sổ game. Hãy mở game rồi nhấn Phát lại."))
                    return False
                if not self.focus_service.activate(window):
                    self._last_play_failure = "focus"
                    self._show_error(
                        tr("Windows chưa cho phép chuyển focus sang game. Hãy click vào game "
                        "rồi nhấn Phát."))
                    return False
                self.active_sky_window = window
                self._set_playback_guard(self._guard_for_target(window))
            else:
                self.active_sky_window = None
                self._set_playback_guard(None)
        if self.controller.busy:
            self.pending_song = song
            self.controller.stop()
            return True
        self.pending_song = None
        self._configure_session(song, preview)
        return bool(self.controller.play(song))

    def _configure_session(self, song: Song, preview: bool) -> None:
        controller = self.controller
        prefs = self.library_state.preferences.get(song.identity)
        speed = prefs.speed if prefs and prefs.speed else self.settings.speed
        marks = self.loop_marks
        loop = None
        if marks["song"] == song.identity and marks["a"] is not None and marks["b"] is not None:
            loop = (min(marks["a"], marks["b"]), max(marks["a"], marks["b"]))
        start = self.cursor[1] if self.cursor and self.cursor[0] == song.identity else 0
        for name, value in (("speed", speed), ("start_ms", 0 if loop else start),
                            ("loop_range", loop), ("preview", preview)):
            try:
                setattr(controller, name, value)
            except AttributeError:
                pass
        setter = getattr(controller, "set_layout", None)
        if callable(setter):
            setter(self.settings.keyboard_layout, self._key_map())
        self._session_preview = preview
        self.dock.set_speed(speed)
        self.dock.runway.set_speed(speed)

    def _play_queued_song(self, song: Song) -> None:
        if self.play_song(song):
            self._session_from_queue = True
            self.queue.remove_song(song)

    @Slot(list, bool)
    def play_all(self, songs: list[Song], shuffle: bool = False) -> bool:
        """Replace the queue with playable ``songs`` and start the first one."""
        if self._closing:
            return False
        playable = [song for song in songs if song.playable]
        if not playable:
            self._show_error(tr("Không có bài phát được trong danh sách đang hiển thị."))
            return False
        if shuffle:
            self._rng.shuffle(playable)
        self.queue.replace_songs(playable)
        if not self.queue.isVisible():
            self.queue_toggle.setChecked(True)
        return self._start_from_queue()

    def toggle_play(self) -> None:
        if self._closing:
            return
        state = self.controller.state
        if state == "focus_paused":
            window = self.active_sky_window
            if (window is None or not self._valid_sky_target(window)
                    or not self.focus_service.activate(window)):
                self._show_error(tr("Hãy mở và chọn cửa sổ game trước khi tiếp tục."))
                return
            self.controller.resume_for_focus()
            self.focus_paused = False
            return
        if state in {"playing", "paused"}:
            self.controller.toggle_pause()
            return
        song = self.library_page.selected_song() or self.current_song
        if song is not None:
            self.play_song(song)
        elif self.queue.peek_next() is not None:
            self._start_from_queue()

    def play_next(self) -> None:
        if self._closing:
            return
        if self.queue.peek_next() is None:
            self.dock.set_status(tr("Hàng chờ đang trống."), "warning")
            return
        self._start_from_queue()

    def stop_playback(self) -> None:
        """Route Stop to the controller currently owned by the window."""
        self._command_generation += 1
        self.pending_song = None
        self.controller.stop()

    def _play_if_current(self, song: Song, generation: int) -> None:
        if not self._closing and generation == self._command_generation:
            self.play_song(song)

    def _play_queue_if_current(self, song: Song, generation: int) -> None:
        if not self._closing and generation == self._command_generation:
            self._start_from_queue()

    def _start_from_queue(self) -> bool:
        """Play the first queued song that can play; drop the ones that never can.

        A song that is unplayable (broken sheet, unsupported keys) is removed and
        reported in the queue panel. A temporary failure such as a missing game
        window keeps the queue intact so the player can retry.
        """
        skipped: list[str] = []
        started = False
        while (song := self.queue.peek_next()) is not None:
            if self.play_song(song):
                self._session_from_queue = True
                self.queue.remove_first_if(song)
                started = True
                break
            if self._last_play_failure != "unplayable":
                break
            self.queue.remove_first_if(song)
            skipped.append(song.title)
        if skipped:
            names = ", ".join(skipped[:3]) + ("..." if len(skipped) > 3 else "")
            self.queue.show_note(tr("Đã bỏ qua {count} bài chưa phát được: {names}").format(
                count=len(skipped), names=names))
            if not started and self.queue.peek_next() is None:
                self._show_error(tr("Hàng chờ không còn bài nào phát được. Đã bỏ qua: "
                                    "{names}").format(names=names))
        return started

    @Slot(object)
    def add_to_queue(self, song: Song) -> bool:
        if not song.playable:
            hint = (tr(" Chọn “Gộp mọi lớp về 15 phím” trong chi tiết bài để phát được.")
                    if song.layered else "")
            self._show_error(tr("Bài “{title}” chưa phát được nên chưa thêm vào hàng chờ."
                                ).format(title=song.title) + hint)
            return False
        self.queue.add_song(song)
        self.dock.set_status(tr("Đã thêm “{title}” vào hàng chờ.").format(title=song.title))
        return True

    @Slot(object)
    def _song_changed(self, song: Song) -> None:
        self.current_song = song
        self.dock.runway.reset()
        self.dock.sync(song, self.controller.state)
        self.mini.sync(song, self.controller.state)
        self._sync_markers(song)

    @Slot(list, int)
    def _timeline_ready(self, moments: list[int], duration: int) -> None:
        self.dock.runway.set_timeline(moments, duration)
        start = getattr(self.controller, "start_ms", 0) or 0
        loop = getattr(self.controller, "loop_range", None)
        if loop:
            start = loop[0]
        if start:
            self.dock.runway.set_progress(start)
        self.mini.set_progress(start, duration)

    def _state_label(self, state: str) -> str:
        label = tr(STATE_LABELS.get(state, state))
        if self._session_preview and state not in {"idle", "error"}:
            label = tr("Xem trước · {0}").format(label.lower())
        return label

    @Slot(str)
    def _state_changed(self, state: str) -> None:
        song = self.current_song
        self.dock.sync(song, state)
        label = self._state_label(state)
        self.mini.sync(song, state, label)
        if state == "error":
            self.dock.runway.set_playing(False)
        elif state in {"countdown", "starting"}:
            self.dock.runway.set_playing(False)
            self.dock.set_status(tr("Đang chuẩn bị") if not self._session_preview else label)
        elif state == "focus_paused":
            self.dock.runway.set_playing(False)
            self.dock.set_status(tr("Game mất focus · bản nhạc đã tạm dừng"), "warning")
            self.dock.play_button.setText(tr("Trở lại game"))
            self.mini.play_button.setText(tr("Trở lại game"))
            if not self.isVisible() and self.tray is not None:
                self.tray.notify(
                    tr("Đã tạm dừng"), tr("Game mất focus. Click vào game để tiếp tục."))
        elif self._session_preview and state != "idle":
            self.dock.set_status(label, "info")
        if self.tray is not None:
            self.tray.set_status(song.title if song else None, label)

    @Slot(int)
    def _countdown_status(self, remaining: int) -> None:
        tail = "" if self._session_preview else tr(" — hãy click vào cửa sổ game")
        self.dock.set_status(tr("Bắt đầu sau {remaining} giây{tail}").format(
            remaining=remaining, tail=tail))
        self.mini.status.setText(tr("Bắt đầu sau {remaining} giây").format(remaining=remaining))

    @Slot(int)
    def _progress_status(self, elapsed: int) -> None:
        self.dock.runway.set_progress(elapsed)
        if self.sheet_editor is not None and self._preview_override is not None:
            self.sheet_editor.set_progress(elapsed)
        self.mini.set_progress(elapsed, self.dock.runway.duration)

    @Slot(list)
    def _keys_pressed(self, keys: list) -> None:
        if self.key_strip.isVisible():
            self.key_grid.flash(keys)
        if self.sheet_editor is not None and self._preview_override is not None:
            self.sheet_editor.flash_keys(keys)
        if self._session_preview and self.settings.preview_sound:
            labels = list(self._key_map().values())
            self.synth.play_indices([labels.index(key) for key in keys if key in labels])

    @Slot(object)
    def _record_play(self, song: Song) -> None:
        if self._session_preview:
            return
        identity = song.identity
        now = time.time()
        history = [HistoryEntry(identity, now)] + [
            entry for entry in self.library_state.history if entry.path != identity]
        counts = dict(self.library_state.play_counts)
        counts[identity] = counts.get(identity, 0) + 1
        self._save_state(replace(self.library_state,
                                 history=tuple(history[:LibraryStateRepository.HISTORY_LIMIT]),
                                 play_counts=counts))
        self.songs = [replace(item, play_count=counts[identity], last_played=now)
                      if item.identity == identity else item for item in self.songs]
        self.library_page.set_songs(self.songs)

    @Slot(bool)
    def _playback_finished(self, completed: bool) -> None:
        self.focus_paused = False
        self.active_sky_window = None
        self._set_playback_guard(None)
        self.dock.runway.reset()
        self.key_grid.clear()
        if self._preview_override is not None:
            self._preview_override = None
            if self._restore_countdown is not None:
                self.controller.countdown = self._restore_countdown
                self._restore_countdown = None
        from_queue, self._session_from_queue = self._session_from_queue, False
        if self._closing:
            self.pending_song = None
        elif self.pending_song:
            song, self.pending_song = self.pending_song, None
            generation = self._command_generation
            QTimer.singleShot(0, lambda s=song, g=generation: self._play_if_current(s, g))
        elif completed:
            finished = self.current_song
            generation = self._command_generation
            if self.queue.repeat_mode == "one" and finished is not None:
                QTimer.singleShot(0, lambda s=finished, g=generation: self._play_if_current(s, g))
            else:
                if self.queue.repeat_mode == "all" and finished is not None:
                    self.queue.add_song(finished)
                next_song = self.queue.peek_next()
                if next_song:
                    QTimer.singleShot(0, lambda s=next_song, g=generation:
                                      self._play_queue_if_current(s, g))
                elif from_queue and self.tray is not None and not self.isVisible():
                    self.tray.notify(
                        tr("Hết hàng chờ"), tr("Đã phát xong tất cả bài trong hàng chờ."))
        if not self._closing and self.controller.state != "error" and not self.pending_song:
            if completed and from_queue and not self.queue.peek_next() \
                    and self.queue.repeat_mode == "off":
                self.dock.set_status(tr("Đã phát xong · hết hàng chờ"), "success")
            else:
                self.dock.set_status(tr("Đã phát xong") if completed else tr("Đã dừng"))
        if self.close_pending:
            self.close_pending = False
            QTimer.singleShot(0, self.close)

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self.dock.set_status(tr("Cần xử lý: {message}").format(message=message), "danger")
        self.mini.status.setText(tr("Cần xử lý — mở cửa sổ chính"))

    # ------------------------------------------------------ speed, A–B
    @Slot(float)
    def set_speed(self, value: float) -> None:
        try:
            self.controller.speed = value
        except AttributeError:
            pass
        self.dock.runway.set_speed(value)
        song = self.current_song if self.controller.busy else self.library_page.selected_song()
        if song is not None:
            self._set_preference(song, speed=None if abs(value - 1.0) < 1e-9 else value)

    def _set_preference(self, song: Song, **changes) -> None:
        current = self.library_state.preferences.get(song.identity, SongPreference())
        updated = replace(current, **changes)
        preferences = dict(self.library_state.preferences)
        if updated == SongPreference():
            preferences.pop(song.identity, None)
        else:
            preferences[song.identity] = updated
        self._save_state(replace(self.library_state, preferences=preferences))

    def _save_state(self, state: LibraryState) -> bool:
        try:
            if self.state_error:
                self.state_repository.recover(state)
                self.state_error = None
            else:
                self.state_repository.save(state)
        except RepositoryError as exc:
            self._show_error(tr("Không thể lưu lịch sử/tùy chọn bài: {exc}").format(exc=exc))
            return False
        self.library_state = state
        return True

    def _marker_song(self) -> Song | None:
        return self.current_song if self.controller.busy else (
            self.library_page.selected_song() or self.current_song)

    @Slot(int)
    def set_cursor(self, position: int) -> None:
        song = self._marker_song()
        if song is None:
            return
        self.cursor = (song.identity, position)
        self._sync_markers(song)
        self.dock.set_status(tr("Sẽ phát từ {0} · nhấn Phát").format(
            format_duration(position)), "info")

    def set_loop_mark(self, which: str) -> None:
        song = self._marker_song()
        runway = self.dock.runway
        if song is None or not runway.duration or runway.duration <= 1:
            self.dock.set_status(tr("Chọn bài rồi bấm vào Note Runway để chọn vị trí trước."),
                                 "warning")
            return
        if self.controller.busy:
            position = runway.elapsed
        elif self.cursor and self.cursor[0] == song.identity:
            position = self.cursor[1]
        else:
            position = 0 if which == "a" else runway.duration
        if self.loop_marks["song"] != song.identity:
            self.loop_marks = {"song": song.identity, "a": None, "b": None}
        self.loop_marks[which] = position
        self._sync_markers(song)
        a, b = self.loop_marks["a"], self.loop_marks["b"]
        if a is not None and b is not None:
            if abs(a - b) < 500:
                self.loop_marks[which] = None
                self._sync_markers(song)
                self.dock.set_status(tr("Đoạn A–B cần dài ít nhất 0,5 giây."), "warning")
                return
            tail = (tr(" Áp dụng từ lần phát tới.") if self.controller.busy
                    else tr(" Nhấn Phát để luyện."))
            self.dock.set_status(
                tr("Lặp đoạn {0}–{1}.{tail}").format(
                    format_duration(min(a, b)), format_duration(max(a, b)), tail=tail),
                "info")
        else:
            self.dock.set_status(tr("Đã đặt {0} tại {1}.").format(
                which.upper(), format_duration(position)), "info")

    def clear_loop(self) -> None:
        self.loop_marks = {"song": None, "a": None, "b": None}
        self.cursor = None
        self._sync_markers(self._marker_song())
        self.dock.set_status(tr("Đã bỏ đoạn lặp và vị trí bắt đầu."))

    def _sync_markers(self, song: Song | None) -> None:
        runway = self.dock.runway
        identity = song.identity if song else None
        same = identity is not None and self.loop_marks["song"] == identity
        runway.loop_a = self.loop_marks["a"] if same else None
        runway.loop_b = self.loop_marks["b"] if same else None
        runway.cursor_ms = self.cursor[1] if self.cursor and self.cursor[0] == identity else None
        runway.update()

    # ------------------------------------------------------- preview mode
    @Slot(bool)
    def set_preview_mode(self, enabled: bool) -> None:
        if self.controller.busy:
            blocker = QSignalBlocker(self.dock.preview_button)
            self.dock.preview_button.setChecked(self.preview_mode)
            del blocker
            self.dock.set_status(tr("Hãy dừng bài trước khi đổi chế độ Xem trước."), "warning")
            return
        self.preview_mode = enabled
        if enabled:
            self.dock.keyboard_button.setChecked(True)
            self.dock.set_status(tr("Xem trước: phát trên bàn phím ảo, không gửi phím ra game."),
                                 "info")
        else:
            self.dock.set_status(tr("Đã tắt Xem trước. Lần phát tới sẽ gửi phím vào game."))

    # ----------------------------------------------------------- favorites
    @Slot(object)
    def toggle_favorite(self, song: Song) -> None:
        updated = [replace(item, favorite=not item.favorite) if item.path == song.path else item
                   for item in self.songs]
        try:
            self.library.save_favorites(item.identity for item in updated if item.favorite)
        except RepositoryError as exc:
            self._show_error(tr("Không thể lưu danh sách yêu thích: {exc}").format(exc=exc))
            return
        self.songs = updated
        self.library_page.set_songs(updated)

    @Slot(object, object)
    def set_layer_policy(self, song: Song, policy: str | None) -> None:
        self._set_preference(song, layer_policy=policy)
        self.refresh_library()
        refreshed = self._song_for(song.identity)
        if refreshed is not None:
            self.library_page.select_song(refreshed)
            self.dock.set_status(
                tr("“{title}”: {result}.").format(
                    title=song.title,
                    result=tr("đã phát được") if refreshed.playable else tr("vẫn bị chặn")),
                "success" if refreshed.playable else "warning")

    # -------------------------------------------------------- sheet editor
    def open_sheet_editor(self, song: Song | None = None) -> SheetEditorDialog | None:
        song = song or self.library_page.selected_song()
        relative = self._relative_or_none(song) if song is not None else None
        if song is None or relative is None:
            self._show_error(tr("Hãy chọn một bài trong thư viện để chỉnh."))
            return None
        try:
            sheet = self.library.load(relative)
        except RepositoryError as exc:
            self._show_error(tr("Không đọc được sheet để chỉnh: {exc}").format(exc=exc))
            return None
        events = [(note.time, tuple(note.keys)) for note in sheet.notes]
        dialog = SheetEditorDialog(song, events, list(self._key_map().values()), self)
        dialog.preview_requested.connect(self.preview_events)
        dialog.stop_preview_requested.connect(self.stop_playback)
        dialog.save_requested.connect(
            lambda name, result: self.save_edited_sheet(name, result, song, dialog))
        dialog.finished.connect(lambda _: self._close_sheet_editor(dialog))
        self.sheet_editor = dialog
        dialog.open()
        return dialog

    def _close_sheet_editor(self, dialog: SheetEditorDialog | TextSheetDialog) -> None:
        if self._preview_override is not None:
            self.stop_playback()
        if self.sheet_editor is dialog:
            self.sheet_editor = None

    def preview_events(self, events: list, title: str) -> bool:
        """Play edited events on the virtual keyboard only; never sends OS keys."""
        if self._closing:
            return False
        if self.controller.busy:
            self.dock.set_status(tr("Hãy dừng bài đang phát trước khi nghe thử."), "warning")
            return False
        key_map = self._key_map()
        missing = sorted({key for _, keys in events for key in keys if key not in key_map})
        if missing:
            message = tr("Bản chỉnh còn phím chưa hỗ trợ: {keys}.").format(
                keys=", ".join(missing[:5]))
            self._show_error(message)
            if self.sheet_editor is not None:
                self.sheet_editor.show_error(message)
            return False
        if not events:
            return False
        moments = sorted({int(time) for time, _ in events})
        song = Song(self.library.root / "__preview__.json", title or tr("Bản chỉnh"),
                    relative="")
        self._preview_override = (song, (list(events), moments, moments[-1]))
        self._restore_countdown = self.controller.countdown
        self.controller.countdown = 0
        self.pending_song = None
        self._set_playback_guard(None)
        self._configure_session(song, True)
        for name, value in (("start_ms", 0), ("loop_range", None)):
            try:
                setattr(self.controller, name, value)
            except AttributeError:
                pass
        if not self.controller.play(song):
            self._preview_override = None
            self.controller.countdown = self._restore_countdown
            self._restore_countdown = None
            return False
        return True

    def save_edited_sheet(self, name: str, events: list, source: Song | None,
                          dialog: SheetEditorDialog | TextSheetDialog | None = None
                          ) -> Path | None:
        if not events:
            return None
        payload = to_sheet_payload(name, events,
                                   source=source.identity if source is not None else None)
        try:
            path = save_new_sheet(self.library.root, name, payload)
        except OSError as exc:
            message = tr("Không thể lưu bản chỉnh: {exc}").format(exc=exc)
            self._show_error(message)
            if dialog is not None:
                dialog.show_error(message)
            return None
        self.refresh_library()
        created = self._song_for(self.library.relative_id(path))
        if created is not None:
            self.library_page.select_song(created)
        self.dock.set_status(tr("Đã lưu bản chỉnh “{name}”.").format(name=path.name), "success")
        if dialog is not None:
            dialog.show_saved(path.name)
        return path

    # ------------------------------------------------------- text and batch
    def open_text_import(self) -> TextSheetDialog:
        dialog = TextSheetDialog(self._key_map(), self)
        dialog.preview_requested.connect(self.preview_events)
        dialog.stop_preview_requested.connect(self.stop_playback)
        dialog.save_requested.connect(
            lambda name, events: self.save_edited_sheet(name, events, None, dialog))
        dialog.finished.connect(lambda _: self._close_sheet_editor(dialog))
        self.sheet_editor = dialog
        dialog.open()
        return dialog

    def choose_batch_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, tr("Chọn thư mục sheet đã tải về"), str(Path.home()))
        if folder:
            self.batch_process([Path(folder)])

    def batch_process(self, sources: list[Path], *, confirm: bool = True,
                      merge: bool = True, fix_timing: bool = True,
                      skip_review: bool = False) -> list[Path]:
        keys = list(self._key_map().keys())

        def run(merge_layers_: bool, fix: bool):
            return batch.analyze(sources, keys, merge=merge_layers_, fix_timing=fix)

        items = run(merge, fix_timing)
        if not items:
            self._show_error(tr("Không có file .txt/.json nào để nhập."))
            return []
        if confirm:
            dialog = BatchDialog(items, run, self)
            if not dialog.exec():
                return []
            selected = dialog.selected_items()
        else:
            selected = [item for item in items if item.importable
                        and not (skip_review and item.status == "review")]
        return self.apply_batch(selected)

    def apply_batch(self, items: list) -> list[Path]:
        records = []
        errors: list[str] = []
        for item in items:
            try:
                if item.changed and item.events:
                    payload = to_sheet_payload(item.title, item.events, source=item.source.name)
                    path = save_new_sheet(self.library.root, item.source.stem, payload)
                    records.append(ImportRecord(path, None, path_fingerprint(path)))
                else:
                    record = self.library.import_with_undo(
                        self.library.inspect_import(item.source), "rename")
                    if record is not None:
                        records.append(record)
            except (OSError, RepositoryError) as exc:
                errors.append(f"{item.source.name}: {exc}")
        self._last_import = records
        self.library_page.show_undo_import(len(records))
        self.refresh_library()
        review = sum(item.status == "review" for item in items)
        message = tr("Đã thêm {count} bài từ thư mục").format(count=len(records))
        if review:
            message += tr("; {count} bài nên nghe thử lại").format(count=review)
        if errors:
            self._show_error(message + tr("; {0} lỗi: {1}").format(len(errors), errors[0]))
        else:
            self.dock.set_status(message + ".", "success" if not review else "warning")
        return [record.path for record in records]

    # ------------------------------------------------------------- import
    def choose_import_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, tr("Nhập sheet"), str(Path.home()), tr("Sheet nhạc (*.txt *.json)"))
        if files:
            self.import_paths([Path(file) for file in files])

    def import_paths(self, sources: list[Path], *, action: str | None = None,
                     confirm: bool = True) -> list[Path]:
        files: list[Path] = []
        for source in sources:
            if source.is_dir():
                files.extend(path for path in sorted(source.rglob("*"))
                             if path.is_file() and path.suffix.lower() in SHEET_SUFFIXES)
            elif source.is_file():
                files.append(source)
        if not files:
            self._show_error(tr("Không có file .txt/.json nào để nhập."))
            return []
        candidates = [self.library.inspect_import(path) for path in files]
        if confirm:
            dialog = ImportDialog(candidates, self)
            if not dialog.exec():
                return []
            action = dialog.conflict_action
        imported: list[Path] = []
        records = []
        errors: list[str] = []
        for candidate in candidates:
            try:
                record = self.library.import_with_undo(candidate, action or "rename")
            except RepositoryError as exc:
                errors.append(str(exc))
                continue
            if record is not None:
                records.append(record)
                imported.append(record.path)
        self._last_import = records
        self.library_page.show_undo_import(len(records))
        self.refresh_library()
        if imported:
            first = self._song_for(self.library.relative_id(imported[0]))
            if first is not None:
                self.show_page(0)
                self.library_page.select_song(first)
        skipped = len(candidates) - len(imported) - len(errors)
        message = tr("Đã nhập {0} bài").format(len(imported))
        if skipped:
            message += tr(", bỏ qua {skipped}").format(skipped=skipped)
        if errors:
            self._show_error(message + tr("; {0} lỗi: {1}").format(len(errors), errors[0]))
        else:
            self.dock.set_status(message + ".", "success")
        return imported

    def undo_last_import(self) -> tuple[int, int]:
        records, self._last_import = self._last_import, []
        self.library_page.show_undo_import(0)
        if not records:
            return 0, 0
        undone, kept = self.library.undo_import(records)
        self.refresh_library()
        message = tr("Đã hoàn tác {count} bài vừa nhập.").format(count=undone)
        if kept:
            message += tr(" Giữ lại {count} bài đã bị sửa sau khi nhập.").format(count=kept)
        self.dock.set_status(message, "success" if not kept else "warning")
        return undone, kept

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(Path(url.toLocalFile()).is_dir()
               or Path(url.toLocalFile()).suffix.lower() in SHEET_SUFFIXES for url in urls):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths_ = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        event.acceptProposedAction()
        QTimer.singleShot(0, lambda: self.import_paths(paths_))

    # ---------------------------------------------------------- playlists
    def save_playlist(self, name: str | None = None) -> bool:
        songs = self.queue.songs()
        if not songs:
            self._show_error(tr("Hàng chờ đang trống; không có gì để lưu."))
            return False
        if name is None:
            name, accepted = QInputDialog.getText(self, tr("Lưu playlist"), tr("Tên playlist:"))
            if not accepted:
                return False
        name = name.strip()
        if not name:
            self._show_error(tr("Tên playlist không được để trống."))
            return False
        playlists = dict(self.library_state.playlists)
        playlists[name] = tuple(song.identity for song in songs)
        if self._save_state(replace(self.library_state, playlists=playlists)):
            self.queue.set_playlists(sorted(playlists))
            self.dock.set_status(tr("Đã lưu playlist “{name}” ({0} bài).").format(
                len(songs), name=name), "success")
            return True
        return False

    def load_playlist(self, name: str) -> bool:
        identities = self.library_state.playlists.get(name)
        if identities is None:
            return False
        songs = [self._song_for(identity) for identity in identities]
        found = [song for song in songs if song is not None]
        self.queue.replace_songs(found)
        missing = len(songs) - len(found)
        if missing:
            self._show_error(tr("Playlist “{name}”: {missing} bài không còn trong thư viện "
                             "và đã được bỏ qua.").format(name=name, missing=missing))
        else:
            self.dock.set_status(
                tr("Đã mở playlist “{name}” vào hàng chờ. Nhấn Tiếp để phát.").format(name=name),
                                 "success")
        if not self.queue.isVisible():
            self.queue_toggle.setChecked(True)
        return True

    def delete_playlist(self, name: str) -> None:
        playlists = dict(self.library_state.playlists)
        if playlists.pop(name, None) is None:
            return
        if self._save_state(replace(self.library_state, playlists=playlists)):
            self.queue.set_playlists(sorted(playlists))
            self.dock.set_status(tr("Đã xóa playlist “{name}”.").format(name=name))

    # -------------------------------------------------------- focus lock
    def _locate_sky_window(self) -> WindowInfo | None:
        if self.sky_window is not None and self._valid_sky_target(self.sky_window):
            return self.sky_window
        self.sky_window = self.focus_service.find_sky_window()
        return self.sky_window

    def _valid_sky_target(self, window: WindowInfo) -> bool:
        validator = getattr(self.focus_service, "validate_target", None)
        if callable(validator):
            return bool(validator(window))
        return bool(self.focus_service.is_window(window))

    def _set_playback_guard(self, guard) -> None:
        setter = getattr(self.controller, "set_input_guard", None)
        if callable(setter):
            setter(guard)

    def _guard_for_target(self, window: WindowInfo):
        def target_is_foreground() -> bool:
            if not self.settings.focus_lock_enabled:
                return True
            return self._valid_sky_target(window) and self.focus_service.is_foreground(window)
        return target_is_foreground

    def _test_window(self) -> tuple[str, str]:
        self.sky_window = None
        window = self._locate_sky_window()
        if window is None:
            return tr("Không tìm thấy cửa sổ game. Hãy mở game rồi thử lại."), "danger"
        return tr("Đã tìm thấy: {title}").format(title=window.title), "info"

    def _poll_focus_lock(self) -> None:
        if (not self.settings.focus_lock_enabled or not self.controller.busy
                or self._session_preview):
            return
        window = self.active_sky_window or self._locate_sky_window()
        focused = window is not None and self.focus_service.is_foreground(window)
        if not focused and not self.focus_paused:
            if self.controller.pause_for_focus():
                self.focus_paused = True
                self.dock.set_status(tr("Game mất focus · bản nhạc đã tạm dừng"), "warning")
        elif focused and self.focus_paused and self.settings.resume_on_sky_focus:
            if self.controller.resume_for_focus():
                self.focus_paused = False
                self.dock.set_status(tr("Đã quay lại game · đang tiếp tục"))

    def _set_focus_lock(self, enabled: bool) -> None:
        checkbox = self.settings_page.focus_lock_checkbox
        if self.controller.busy:
            blocker = QSignalBlocker(checkbox)
            checkbox.setChecked(self.settings.focus_lock_enabled)
            del blocker
            self.dock.set_status(tr("Hãy dừng bài trước khi đổi chế độ khóa vào game."), "warning")
            return
        if not self._save_settings(focus_lock_enabled=enabled):
            blocker = QSignalBlocker(checkbox)
            checkbox.setChecked(self.settings.focus_lock_enabled)
            del blocker
            return
        if not enabled:
            self._set_playback_guard(None)
            self.active_sky_window = None

    def _set_resume_on_focus(self, enabled: bool) -> None:
        if not self._save_settings(resume_on_sky_focus=enabled):
            checkbox = self.settings_page.resume_focus_checkbox
            blocker = QSignalBlocker(checkbox)
            checkbox.setChecked(self.settings.resume_on_sky_focus)
            del blocker

    def pick_target_window(self) -> None:
        lister = getattr(self.focus_service, "windows", None)
        windows = pickable_windows(lister()) if callable(lister) else []
        dialog = WindowPickerDialog(windows, self)
        if dialog.exec():
            exe = dialog.selected_exe()
            if exe:
                self._set_target_exe(exe)

    def _set_target_exe(self, exe: str | None) -> None:
        if self.controller.busy:
            self.dock.set_status(tr("Hãy dừng bài trước khi đổi cửa sổ mục tiêu."), "warning")
            return
        if exe is not None and exe.casefold() == "sky.exe":
            exe = None
        if self._save_settings(focus_target_exe=exe):
            if hasattr(self.focus_service, "target_exe"):
                self.focus_service.target_exe = exe
            self.sky_window = None
            self.settings_page.set_target(exe)
            self.dock.set_status(tr("Mục tiêu khóa focus: {0}.").format(exe or 'Sky'), "info")

    # ----------------------------------------------------------- settings
    def _apply_settings(self) -> None:
        page = self.settings_page
        widgets = (page.key_layout, page.countdown, page.always_on_top, page.reduced_motion,
                   page.minimize_to_tray, page.preview_sound, page.focus_lock_checkbox,
                   page.resume_focus_checkbox, page.check_updates, page.language)
        blockers = [QSignalBlocker(widget) for widget in widgets]
        try:
            index = page.key_layout.findData(self.settings.keyboard_layout)
            page.key_layout.setCurrentIndex(max(0, index))
            page.custom_keys.setText("".join(self.settings.custom_layout_keys))
            page.countdown.setValue(self.settings.countdown_seconds)
            page.countdown_value.setText(tr("{countdown_seconds} giây").format(
                countdown_seconds=self.settings.countdown_seconds))
            page.always_on_top.setChecked(self.settings.always_on_top)
            page.reduced_motion.setChecked(self.settings.reduced_motion)
            page.minimize_to_tray.setChecked(self.settings.minimize_to_tray)
            page.preview_sound.setChecked(self.settings.preview_sound)
            page.focus_lock_checkbox.setChecked(self.settings.focus_lock_enabled)
            page.resume_focus_checkbox.setChecked(self.settings.resume_on_sky_focus)
            page.check_updates.setChecked(self.settings.check_updates)
            page.language.setCurrentIndex(max(0, page.language.findData(self.settings.language)))
        finally:
            del blockers
        page.set_target(self.settings.focus_target_exe)
        key_map = self._key_map()
        setter = getattr(self.controller, "set_layout", None)
        if callable(setter):
            setter(self.settings.keyboard_layout, key_map)
        else:
            self.controller.layout_name = self.settings.keyboard_layout
        self.controller.countdown = self.settings.countdown_seconds
        self.key_grid.set_labels(list(key_map.values()))
        self.hotkeys_page.set_music_keys(key_map.values())
        self._apply_mini_on_top(self.settings.always_on_top)
        self.dock.runway.set_reduced_motion(self.settings.reduced_motion)
        self.dock.set_speed(self.settings.speed)
        self.setWindowOpacity(max(.85, self.settings.window_opacity))

    def _save_settings(self, **changes) -> bool:
        updated = replace(self.settings, **changes)
        try:
            if self.settings_error:
                backup = self.settings_repository.recover(updated)
                self.settings_error = None
                if backup is not None:
                    self.dock.set_status(
                        tr("Đã sao lưu cấu hình lỗi tại {name} và lưu cấu hình mới.").format(
                            name=backup.name))
            else:
                self.settings_repository.save(updated)
        except RepositoryError as exc:
            self._show_error(tr("Không thể lưu cài đặt: {exc}").format(exc=exc))
            return False
        self.settings = updated
        return True

    def _save_or_restore(self, **changes) -> bool:
        if self._save_settings(**changes):
            return True
        self._apply_settings()
        return False

    def _set_layout(self, value: str) -> None:
        if value == "custom" and not self.settings.custom_layout_keys:
            self._apply_settings()
            self.dock.set_status(tr("Nhập 15 phím vào ô Phím tùy chỉnh rồi nhấn Lưu bộ tùy chỉnh."),
                                 "warning")
            return
        if self._save_or_restore(keyboard_layout=value):
            self._apply_settings()
            self.refresh_library()

    def _save_custom_layout(self, text: str) -> None:
        try:
            keys = tuple(MacroPlayer.layout_map(list(text.strip())).values())
        except ValueError as exc:
            self._show_error(str(exc))
            return
        if self._save_or_restore(custom_layout_keys=keys, keyboard_layout="custom"):
            self._apply_settings()
            self.refresh_library()
            self.dock.set_status(tr("Đã lưu và dùng bộ phím tùy chỉnh."), "success")

    def _set_language(self, code: str) -> None:
        # Widgets are built once, so the new language is applied on the next start.
        if code != self.settings.language and self._save_or_restore(language=code):
            self.dock.set_status(tr("Đã đổi ngôn ngữ. Mở lại ứng dụng để áp dụng."), "info")

    def _set_countdown(self, value: int) -> None:
        if self._save_or_restore(countdown_seconds=value):
            self.controller.countdown = value

    def _set_mini_on_top(self, value: bool) -> None:
        if self._save_or_restore(always_on_top=value):
            self._apply_mini_on_top(value)

    def _apply_mini_on_top(self, value: bool) -> None:
        visible = self.mini.isVisible()
        self.mini.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, value)
        if self.mini.pin_button.isChecked() != value:
            blocker = QSignalBlocker(self.mini.pin_button)
            self.mini.pin_button.setChecked(value)
            del blocker
        if visible:
            self.mini.show()

    def _set_reduced_motion(self, value: bool) -> None:
        if self._save_or_restore(reduced_motion=value):
            self.dock.runway.set_reduced_motion(value)

    @Slot(object)
    def _save_hotkeys(self, values: Mapping) -> None:
        previous = self.settings
        hotkeys = dict(self.settings.hotkeys)
        hotkeys.update(stop=values["stop"], next=values["next"])
        updated = replace(self.settings, pause_hotkey=values["pause"], hotkeys=hotkeys,
                          hotkey_keys=values["slot_keys"], song_slots=values["song_slots"])
        if not self.hotkeys.start(updated):
            self.hotkeys_page.show_feedback(
                tr("Không thể áp dụng; cấu hình và phím tắt đang dùng được giữ nguyên."), False)
            return
        try:
            if self.settings_error:
                self.settings_repository.recover(updated)
                self.settings_error = None
            else:
                self.settings_repository.save(updated)
        except RepositoryError as exc:
            restored = self.hotkeys.start(previous)
            recovery = (tr("Đã khôi phục phím tắt cũ.") if restored
                        else tr("Không thể khôi phục listener cũ; hãy mở lại ứng dụng."))
            self.hotkeys_page.show_feedback(tr("Không thể lưu cấu hình: {exc}. {recovery}").format(
                exc=exc, recovery=recovery), False)
            return
        self.settings = updated
        self.hotkeys_page.show_feedback(tr("Đã lưu và áp dụng global hotkeys."), True)

    @Slot(int)
    def _play_slot(self, index: int) -> None:
        if self._closing or index >= len(self.settings.song_slots):
            return
        selected = self.settings.song_slots[index]
        if not selected:
            return
        normalized = selected.replace("\\", "/").casefold()
        matches = [song for song in self.songs if song.identity.casefold() == normalized]
        if not matches and "/" not in normalized:
            matches = [song for song in self.songs if song.path.name.casefold() == normalized]
        if len(matches) == 1:
            self.play_song(matches[0])
        elif len(matches) > 1:
            self._show_error(tr("Tên bài cũ bị trùng cho phím {0}: {selected}. "
                             "Hãy gán lại bài bằng đường dẫn đầy đủ.").format(
                                 index + 1, selected=selected))
        else:
            self._show_error(tr("Không tìm thấy bài đã gán cho phím {0}: {selected}").format(
                index + 1, selected=selected))

    def _update_available(self, tag: str, url: str) -> None:
        self.dock.set_status(
            tr("Có bản mới {tag}. Mở Cài đặt → Hỗ trợ hoặc trang Releases để tải.").format(tag=tag),
                             "info")
        self._latest_release_url = url
        if self.tray is not None:
            self.tray.notify(tr("Có bản mới"), tr("Sky Macro Player {tag} đã phát hành.").format(
                tag=tag))
        answer = QMessageBox.question(
            self, tr("Có bản mới"),
            tr("Sky Macro Player {tag} đã phát hành. Mở trang tải về?").format(tag=tag))
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(url))

    # ----------------------------------------------- guide, palette, report
    def run_onboarding(self) -> None:
        hotkeys = with_legacy_defaults(self.settings).hotkeys
        wizard = OnboardingWizard(
            layout_name=self.settings.keyboard_layout,
            focus_lock=self.settings.focus_lock_enabled,
            stop_key=hotkeys.get("stop", "f10"), pause_key=self.settings.pause_hotkey,
            next_key=hotkeys.get("next", "f11"),
            test_window=lambda: self._test_window()[0], parent=self)
        accepted = bool(wizard.exec())
        changes: dict = {"first_run_completed": True}
        if accepted:
            changes.update(wizard.values())
        if self._save_or_restore(**changes):
            self._apply_settings()
            if accepted:
                self.refresh_library()

    def open_command_palette(self) -> None:
        commands: list[tuple[str, Callable[[], object]]] = [
            (tr("Phát / Tạm dừng"), self.toggle_play),
            (tr("Dừng"), self.stop_playback),
            (tr("Bài tiếp theo"), self.play_next),
            ("Mini player", self.toggle_mini),
            (tr("Nhập sheet"), self.choose_import_files),
            (tr("Chỉnh sheet bài đang chọn"), self.open_sheet_editor),
            (tr("Nhập sheet chữ"), self.open_text_import),
            (tr("Xử lý cả thư mục sheet"), self.choose_batch_folder),
            (tr("Phát tất cả bài đang hiển thị"),
             lambda: self.play_all(self.library_page.visible_songs())),
            (tr("Trộn bài đang hiển thị"),
             lambda: self.play_all(self.library_page.visible_songs(), True)),
            (tr("Đổi chế độ lặp"), self.queue.cycle_repeat),
            (tr("Bật/tắt Xem trước"), self.dock.preview_button.toggle),
            (tr("Bật/tắt bàn phím"), self.dock.keyboard_button.toggle),
            (tr("Mở Thư viện"), lambda: self.show_page(0)),
            (tr("Mở Phím tắt"), lambda: self.show_page(1)),
            (tr("Mở Cài đặt"), lambda: self.show_page(2)),
            (tr("Xuất báo cáo chẩn đoán"), self.export_diagnostics),
            (tr("Hướng dẫn thiết lập"), self.run_onboarding),
        ]
        palette = CommandPalette(self.songs, commands, self)
        palette.song_chosen.connect(self.play_song)
        palette.exec()

    def library_summary(self) -> dict:
        return {
            "songs": len(self.songs),
            "playable": sum(song.playable for song in self.songs),
            "layered": sum(song.layered for song in self.songs),
            "unsupported": [song.identity for song in self.songs if not song.playable],
            "layout": self.settings.keyboard_layout,
            "hotkeys_active": bool(getattr(self.hotkeys, "active", False)),
            "focus_target": self.settings.focus_target_exe or "Sky.exe",
        }

    def export_diagnostics(self, destination: Path | None = None) -> Path | None:
        if destination is None:
            default = Path.home() / f"SkyMacroPlayer-chan-doan-{time.strftime('%Y%m%d-%H%M')}.zip"
            chosen, _ = QFileDialog.getSaveFileName(
                self, tr("Lưu báo cáo chẩn đoán"), str(default), "Zip (*.zip)")
            if not chosen:
                return None
            destination = Path(chosen)
        try:
            build_report(destination, settings=self.settings,
                         library_summary=self.library_summary(),
                         log_dir=paths.user_data_dir() / "logs",
                         extra={"state": self.controller.state})
        except OSError as exc:
            self._show_error(tr("Không thể tạo báo cáo: {exc}").format(exc=exc))
            return None
        self.dock.set_status(tr("Đã lưu báo cáo chẩn đoán: {name}").format(
            name=destination.name), "success")
        return destination

    # ------------------------------------------------------ mini and tray
    def toggle_mini(self) -> None:
        if self.mini.isVisible():
            self._hide_mini()
        else:
            self.mini.sync(self.current_song, self.controller.state,
                           self._state_label(self.controller.state))
            self.mini.restore_position(self._mini_position)
            self.mini.show()
            self.mini.raise_()

    def _hide_mini(self) -> None:
        self.mini.hide()
        if self._mini_position and self._mini_position != self.settings.mini_position:
            self._save_settings(mini_position=tuple(self._mini_position))

    def _expand_from_mini(self) -> None:
        self._show_from_tray()
        self._hide_mini()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wide = self.width() >= 980
        if wide != self._wide_layout:
            self._wide_layout = wide
            self.queue_toggle.setChecked(wide)
        self.dock.set_compact(self.width() < 900)
        self.rail.setFixedWidth(150 if self.width() < 1000 else 178)

    def closeEvent(self, event) -> None:
        if (self.settings.minimize_to_tray and self.tray is not None and not self._quitting
                and not self._closing):
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.notify(
                    tr("Vẫn đang chạy"), tr("Ứng dụng ở khay hệ thống. Chọn Thoát để tắt."))
            return
        self._closing = True
        self.pending_song = None
        self.focus_timer.stop()
        self.hotkeys.stop()
        if self.controller.busy:
            self.close_pending = True
            self.stop_playback()
            self.dock.set_status(tr("Đang dừng an toàn trước khi đóng"))
            event.ignore()
            return
        if self.mini.isVisible():
            self._hide_mini()
        self.mini.close()
        if self.tray is not None:
            self.tray.hide()
        event.accept()
        self.closed.emit()
