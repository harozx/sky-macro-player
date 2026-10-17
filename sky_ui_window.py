"""Responsive main window orchestration for Sky Instrument Console."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from sky_ui_core import PlaybackController, SheetLibrary, Song, STYLE, Tokens
from macro_player import __version__
from sky_ui_shell import (
    HotkeysPage, LibraryPage, MiniOverlay, PlaybackDock, QueuePanel, SettingsPage,
)


class MainWindow(QMainWindow):
    def __init__(self, library: SheetLibrary | None = None,
                 controller: PlaybackController | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Sky Instrument Console")
        self.setMinimumSize(820, 600)
        self.resize(1220, 760)
        self.setStyleSheet(STYLE)
        self.library_source = library or SheetLibrary()
        self.songs = self.library_source.songs()
        self.controller = controller or PlaybackController(self)
        if self.controller.parent() is None:
            self.controller.setParent(self)
        self.current_song: Song | None = None
        self.pending_song: Song | None = None
        self._closing = False
        self._command_generation = 0
        self.mini = MiniOverlay()

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
        brand = QLabel("Sky Instrument")
        brand.setObjectName("brand")
        tagline = QLabel("CONSOLE")
        tagline.setObjectName("eyebrow")
        rail_layout.addWidget(brand)
        rail_layout.addWidget(tagline)
        rail_layout.addSpacing(28)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.pages = QStackedWidget()
        self.library_page = LibraryPage(self.songs)
        self.hotkeys_page = HotkeysPage()
        self.settings_page = SettingsPage()
        for page in (self.library_page, self.hotkeys_page, self.settings_page):
            self.pages.addWidget(page)
        for index, label in enumerate(("Thư viện", "Phím tắt", "Cài đặt")):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.setAccessibleName(f"Mở {label}")
            button.setChecked(index == 0)
            button.clicked.connect(lambda checked=False, page=index: self.pages.setCurrentIndex(page))
            self.nav_group.addButton(button)
            rail_layout.addWidget(button)
        self.queue_toggle = QPushButton("Hàng chờ")
        self.queue_toggle.setCheckable(True)
        self.queue_toggle.setChecked(True)
        self.queue_toggle.setAccessibleName("Hiện hoặc ẩn hàng chờ")
        rail_layout.addWidget(self.queue_toggle)
        rail_layout.addStretch(1)
        version = QLabel(f"PHIÊN BẢN {__version__}")
        version.setObjectName("eyebrow")
        rail_layout.addWidget(version)
        content.addWidget(self.rail)
        content.addWidget(self.pages, 1)
        self.queue = QueuePanel()
        self.queue_toggle.toggled.connect(self._set_queue_visible)
        content.addWidget(self.queue)
        self.dock = PlaybackDock()
        shell.addWidget(self.dock)

        self.library_page.play_requested.connect(self.play_song)
        self.library_page.queue_requested.connect(self.queue.add_song)
        self.library_page.favorite_requested.connect(self.toggle_favorite)
        self.queue.play_requested.connect(self._play_queued_song)
        self.dock.play_requested.connect(self.toggle_play)
        self.dock.next_requested.connect(self.play_next)
        self.dock.stop_requested.connect(self.stop_playback)
        self.dock.mini_requested.connect(self.toggle_mini)
        self.mini.play_requested.connect(self.toggle_play)
        self.mini.next_requested.connect(self.play_next)
        self.mini.stop_requested.connect(self.stop_playback)
        self.mini.expand_requested.connect(self._expand_from_mini)
        self.mini.pin_changed.connect(self.settings_page.always_on_top.setChecked)
        self.controller.song_changed.connect(self._song_changed)
        self.controller.state_changed.connect(self._state_changed)
        self.controller.timeline_ready.connect(self._timeline_ready)
        self.controller.error.connect(self._show_error)
        self.controller.finished.connect(self._playback_finished)
        self.settings_page.reduced_motion_changed.connect(self.dock.runway.set_reduced_motion)
        self.settings_page.layout_changed.connect(self._set_layout)
        self.settings_page.countdown_changed.connect(self._set_countdown)
        self.settings_page.always_on_top.toggled.connect(self._set_mini_on_top)
        self._install_shortcuts()
        if self.songs:
            self.library_page.list.setCurrentRow(0)
        self._wide_layout: bool | None = None

    def _install_shortcuts(self) -> None:
        for shortcut, handler, protect_text_input in (
            ("Space", self.toggle_play, True),
            ("Escape", self.stop_playback, False),
            ("Ctrl+Right", self.play_next, True),
            ("Ctrl+M", self.toggle_mini, False),
            ("Ctrl+F", self.focus_search, False),
        ):
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
            if protect_text_input:
                action.triggered.connect(
                    lambda checked=False, callback=handler:
                    self._run_unless_editing(callback)
                )
            else:
                action.triggered.connect(handler)
            self.addAction(action)

    def _run_unless_editing(self, callback) -> None:
        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QComboBox)):
            return
        callback()

    def focus_search(self) -> None:
        self.pages.setCurrentWidget(self.library_page)
        self.library_page.search.setFocus()
        self.library_page.search.selectAll()

    def _set_queue_visible(self, visible: bool) -> None:
        self.queue.setVisible(visible)
        self.queue_toggle.setText("Ẩn hàng chờ" if visible else "Hiện hàng chờ")

    @Slot(object)
    def play_song(self, song: Song) -> bool:
        if self._closing:
            return False
        if self.controller.busy:
            self.pending_song = song
            self.controller.stop()
            return True
        self.pending_song = None
        return bool(self.controller.play(song))

    def _play_queued_song(self, song: Song) -> None:
        if self.play_song(song):
            for row in range(self.queue.list.count()):
                item = self.queue.list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == song:
                    self.queue.list.takeItem(row)
                    self.queue._sync_hint()
                    break

    def toggle_play(self) -> None:
        if self._closing:
            return
        if self.controller.state in {"playing", "paused"}:
            self.controller.toggle_pause()
            return
        song = self.current_song or self.library_page.selected_song()
        queued = False
        if song is None:
            song = self.queue.peek_next()
            queued = song is not None
        if song:
            accepted = self.play_song(song)
            if accepted and queued:
                self.queue.remove_first_if(song)

    def play_next(self) -> None:
        if self._closing:
            return
        next_song = self.queue.peek_next()
        if next_song and self.play_song(next_song):
            self.queue.remove_first_if(next_song)

    def stop_playback(self) -> None:
        """Route Stop to the controller currently owned by the window."""
        self._command_generation += 1
        self.pending_song = None
        self.controller.stop()

    def _play_if_current(self, song: Song, generation: int) -> None:
        if not self._closing and generation == self._command_generation:
            self.play_song(song)

    def _play_queue_if_current(self, song: Song, generation: int) -> None:
        if (not self._closing and generation == self._command_generation
                and self.play_song(song)):
            self.queue.remove_first_if(song)

    @Slot(object)
    def toggle_favorite(self, song: Song) -> None:
        self.songs = [
            Song(item.path, item.title, not item.favorite) if item.path == song.path else item
            for item in self.songs
        ]
        self.library_page.songs = self.songs
        self.library_page.rebuild()
        try:
            self.library_source.favorites.save(
                item.identity for item in self.songs if item.favorite
            )
        except OSError as exc:
            self._show_error(f"Không thể lưu danh sách yêu thích: {exc}")

    def toggle_mini(self) -> None:
        if self.mini.isVisible():
            self.mini.hide()
        else:
            self.mini.sync(self.current_song, self.controller.state)
            self.mini.show()
            self.mini.raise_()

    @Slot(object)
    def _song_changed(self, song: Song) -> None:
        self.current_song = song
        self.dock.runway.reset()
        self.dock.sync(song, self.controller.state)
        self.mini.sync(song, self.controller.state)

    @Slot(list, int)
    def _timeline_ready(self, moments: list[int], duration: int) -> None:
        self.dock.runway.set_timeline(moments, duration)
        self.mini.set_progress(0, duration)

    @Slot(str)
    def _state_changed(self, state: str) -> None:
        self.dock.sync(self.current_song, state)
        self.mini.sync(self.current_song, state)

    @Slot(bool)
    def _playback_finished(self, completed: bool) -> None:
        self.dock.runway.reset()
        if self._closing:
            self.pending_song = None
            return
        if self.pending_song:
            song, self.pending_song = self.pending_song, None
            generation = self._command_generation
            QTimer.singleShot(
                0, lambda s=song, g=generation: self._play_if_current(s, g)
            )
        elif completed:
            next_song = self.queue.peek_next()
            if next_song:
                generation = self._command_generation
                QTimer.singleShot(
                    0, lambda s=next_song, g=generation:
                    self._play_queue_if_current(s, g)
                )

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self.dock.status.setText(f"Cần xử lý: {message}")
        self.dock.status.setStyleSheet(f"color: {Tokens.DANGER};")

    def _set_layout(self, value: str) -> None:
        self.controller.layout_name = value

    def _set_countdown(self, value: int) -> None:
        self.controller.countdown = value

    def _set_mini_on_top(self, value: bool) -> None:
        visible = self.mini.isVisible()
        self.mini.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, value)
        if self.mini.pin_button.isChecked() != value:
            self.mini.pin_button.setChecked(value)
        if visible:
            self.mini.show()

    def _expand_from_mini(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.mini.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wide = self.width() >= 980
        if wide != getattr(self, "_wide_layout", None):
            self._wide_layout = wide
            self.queue_toggle.setChecked(wide)
        self.dock.runway.setVisible(self.width() >= 900)
        self.rail.setFixedWidth(150 if self.width() < 1000 else 178)

    def closeEvent(self, event) -> None:
        self._closing = True
        self.pending_song = None
        if self.controller.busy:
            self.stop_playback()
            QMessageBox.information(
                self, "Đang dừng", "Ứng dụng đang nhả các phím. Hãy đóng lại sau một nhịp."
            )
            event.ignore()
            return
        self.mini.close()
        event.accept()
