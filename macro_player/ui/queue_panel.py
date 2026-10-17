"""Queue panel: reorder, repeat modes, shuffle, clear/undo and playlists."""

from __future__ import annotations

import random

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import N_, tr
from ..library import Song
from .theme import Tokens

EMPTY_HINT = N_(
    "Hàng chờ đang trống. Chọn một bài trong thư viện và nhấn “Thêm hàng chờ”.")


class QueuePanel(QWidget):
    play_requested = Signal(object)
    save_playlist_requested = Signal()
    load_playlist_requested = Signal(str)
    delete_playlist_requested = Signal(str)

    REPEAT_LABELS = {"off": N_("Lặp: Tắt"), "all": N_("Lặp: Hàng chờ"),
                     "one": N_("Lặp: Một bài")}

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("queuePanel")
        self.setMinimumWidth(246)
        self.setMaximumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 22, 16, 14)
        eyebrow = QLabel(tr("PHÁT TIẾP"))
        eyebrow.setObjectName("eyebrow")
        title = QLabel(tr("Hàng chờ"))
        title.setFont(QFont(Tokens.DISPLAY, 19, QFont.Weight.DemiBold))
        self.hint = QLabel(tr(EMPTY_HINT))
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.list = QListWidget()
        self.list.setAccessibleName(tr("Hàng chờ phát nhạc"))
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.repeat_mode = "off"
        self.repeat_button = QPushButton()
        self.repeat_button.setAccessibleName(tr("Đổi chế độ lặp"))
        self.repeat_button.setToolTip(
            tr("Tắt → Lặp hàng chờ → Lặp một bài. Dừng luôn kết thúc việc lặp."))
        self._sync_repeat()
        tools = QHBoxLayout()
        self.shuffle_button = QPushButton(tr("Trộn"))
        self.shuffle_button.setToolTip(tr("Xáo trộn thứ tự các bài đang chờ."))
        self.clear_button = QPushButton(tr("Xóa hết"))
        self.playlist_button = QPushButton("Playlist")
        self.playlist_menu = QMenu(self)
        self.playlist_button.setMenu(self.playlist_menu)
        for button in (self.shuffle_button, self.clear_button, self.playlist_button):
            button.setProperty("compact", True)
            tools.addWidget(button)
        self.undo_button = QPushButton(tr("Hoàn tác"))
        self.undo_button.setAccessibleName(tr("Hoàn tác thay đổi hàng chờ"))
        self.undo_button.hide()
        remove = QPushButton(tr("Bỏ bài đã chọn"))
        remove.setProperty("danger", True)
        widget: QWidget
        for widget in (eyebrow, title, self.hint, self.repeat_button):
            layout.addWidget(widget)
        layout.addLayout(tools)
        for widget in (self.list, self.undo_button, remove):
            layout.addWidget(widget)
        layout.setStretchFactor(self.list, 1)
        self.list.itemDoubleClicked.connect(
            lambda item: self.play_requested.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        self.list.model().rowsInserted.connect(lambda *_: self._sync_hint())
        self.list.model().rowsRemoved.connect(lambda *_: self._sync_hint())
        remove.clicked.connect(self._remove)
        self.repeat_button.clicked.connect(self.cycle_repeat)
        self.shuffle_button.clicked.connect(lambda: self.shuffle())
        self.clear_button.clicked.connect(self.clear)
        self.undo_button.clicked.connect(self.undo)
        self._undo_snapshot: list[Song] | None = None
        self.set_playlists([])

    # -- repeat ----------------------------------------------------------
    def _sync_repeat(self) -> None:
        self.repeat_button.setText(tr(self.REPEAT_LABELS[self.repeat_mode]))

    @Slot()
    def cycle_repeat(self) -> None:
        order = ("off", "all", "one")
        self.set_repeat_mode(order[(order.index(self.repeat_mode) + 1) % len(order)])

    def set_repeat_mode(self, mode: str) -> None:
        if mode not in self.REPEAT_LABELS:
            raise ValueError(tr("Chế độ lặp không hợp lệ: {mode}").format(mode=mode))
        self.repeat_mode = mode
        self._sync_repeat()

    # -- playlists -------------------------------------------------------
    def set_playlists(self, names: list[str]) -> None:
        self._playlist_names = list(names)
        menu = self.playlist_menu
        menu.clear()
        save = menu.addAction(tr("Lưu hàng chờ thành playlist…"))
        save.triggered.connect(self.save_playlist_requested)
        save.setEnabled(self.list.count() > 0)
        menu.addSeparator()
        if not names:
            empty = menu.addAction(tr("Chưa có playlist"))
            empty.setEnabled(False)
            return
        for name in names:
            action = menu.addAction(tr("Mở “{name}”").format(name=name))
            action.triggered.connect(lambda _=False, n=name: self.load_playlist_requested.emit(n))
        delete_menu = menu.addMenu(tr("Xóa playlist"))
        for name in names:
            action = delete_menu.addAction(name)
            action.triggered.connect(lambda _=False, n=name: self.delete_playlist_requested.emit(n))

    # -- contents --------------------------------------------------------
    def songs(self) -> list[Song]:
        return [self.list.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(self.list.count())]

    def _set_songs(self, songs: list[Song]) -> None:
        self.list.clear()
        for song in songs:
            self._append(song)
        self._sync_hint()

    def _append(self, song: Song) -> None:
        item = QListWidgetItem(song.title)
        item.setData(Qt.ItemDataRole.UserRole, song)
        item.setToolTip(song.identity)
        self.list.addItem(item)

    def _remember_for_undo(self) -> None:
        self._undo_snapshot = self.songs()
        self.undo_button.setVisible(bool(self._undo_snapshot))

    def replace_songs(self, songs: list[Song]) -> None:
        """Replace the whole queue; the previous queue can be restored once."""
        self._remember_for_undo()
        self._set_songs(songs)

    def shuffle(self, rng: random.Random | None = None) -> None:
        songs = self.songs()
        if len(songs) < 2:
            return
        (rng or random).shuffle(songs)
        self._set_songs(songs)

    @Slot()
    def clear(self) -> None:
        if self.list.count():
            self._remember_for_undo()
            self._set_songs([])

    @Slot()
    def undo(self) -> None:
        if self._undo_snapshot is not None:
            snapshot, self._undo_snapshot = self._undo_snapshot, None
            self._set_songs(snapshot)
        self.undo_button.hide()

    def add_song(self, song: Song) -> None:
        self._append(song)
        self._sync_hint()

    def take_next(self) -> Song | None:
        if not self.list.count():
            return None
        item = self.list.takeItem(0)
        self._sync_hint()
        return item.data(Qt.ItemDataRole.UserRole)

    def peek_next(self) -> Song | None:
        item = self.list.item(0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def remove_first_if(self, song: Song) -> bool:
        first = self.peek_next()
        if first is None or first != song:
            return False
        self.list.takeItem(0)
        self._sync_hint()
        return True

    def remove_song(self, song: Song) -> bool:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == song:
                self.list.takeItem(row)
                self._sync_hint()
                return True
        return False

    def _remove(self) -> None:
        if self.list.currentRow() >= 0:
            self.list.takeItem(self.list.currentRow())
            self._sync_hint()

    def _sync_hint(self) -> None:
        count = self.list.count()
        self.hint.setText(
            tr("{count} bài đang chờ").format(count=count) if count else tr(EMPTY_HINT))
        self.set_playlists(getattr(self, "_playlist_names", []))
