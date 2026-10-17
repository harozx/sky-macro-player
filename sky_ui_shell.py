"""Application shell for the Sky Instrument Console."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider, QStackedWidget,
    QVBoxLayout, QWidget,
)

from macro_core import MacroPlayer
from sky_ui_core import (
    JsonFavoritesStore, NoteRunway, PlaybackController, SheetLibrary, Song,
    STYLE, Tokens,
)


class MiniOverlay(QWidget):
    play_requested, next_requested, stop_requested = Signal(), Signal(), Signal()
    expand_requested, pin_changed = Signal(), Signal(bool)

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Sky Instrument — Mini")
        self.setObjectName("appRoot")
        self.setMinimumSize(440, 96)
        self.resize(520, 96)
        self.setMaximumHeight(118)
        self.setStyleSheet(STYLE)
        row = QHBoxLayout(self)
        text = QVBoxLayout()
        eyebrow = QLabel("ĐANG PHÁT")
        eyebrow.setObjectName("eyebrow")
        self.title = QLabel("Chưa chọn bài")
        self.title.setMinimumWidth(150)
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status = QLabel("Sẵn sàng")
        self.status.setObjectName("muted")
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("eyebrow")
        text.addWidget(eyebrow)
        text.addWidget(self.title)
        text.addWidget(self.status)
        text.addWidget(self.time_label)
        row.addLayout(text, 1)
        self.play_button = QPushButton("Phát")
        self.play_button.setProperty("primary", True)
        self.next_button, self.stop_button = QPushButton("Tiếp"), QPushButton("Dừng")
        self.pin_button, self.expand_button = QPushButton("Ghim"), QPushButton("Mở rộng")
        self.pin_button.setCheckable(True)
        self.pin_button.setChecked(True)
        self.stop_button.setProperty("danger", True)
        for button in (
            self.play_button, self.next_button, self.stop_button,
            self.pin_button, self.expand_button,
        ):
            button.setProperty("compact", True)
            button.setMinimumSize(52, 44)
            row.addWidget(button)
        self.play_button.setAccessibleName("Phát hoặc tạm dừng")
        self.next_button.setAccessibleName("Phát bài tiếp theo")
        self.stop_button.setAccessibleName("Dừng phát nhạc")
        self.play_button.clicked.connect(self.play_requested)
        self.next_button.clicked.connect(self.next_requested)
        self.stop_button.clicked.connect(self.stop_requested)
        self.pin_button.toggled.connect(self.pin_changed)
        self.expand_button.clicked.connect(self.expand_requested)

    def set_progress(self, elapsed: int, duration: int) -> None:
        def stamp(value: int) -> str:
            seconds = max(0, int(value) // 1000)
            return f"{seconds // 60}:{seconds % 60:02d}"
        self.time_label.setText(f"{stamp(elapsed)} / {stamp(duration)}")

    def sync(self, song: Song | None, state: str) -> None:
        self.title.setText(song.title if song else "Chưa chọn bài")
        self.title.setToolTip(song.title if song else "")
        self.status.setText({
            "idle": "Sẵn sàng",
            "countdown": "Đang đếm ngược",
            "starting": "Đang chuẩn bị",
            "playing": "Đang phát",
            "paused": "Đã tạm dừng",
            "focus_paused": "Đang chờ cửa sổ Sky",
            "stopping": "Đang dừng an toàn",
            "error": "Có lỗi phát nhạc",
        }.get(state, state))
        self.play_button.setText(
            "Tiếp tục" if state in {"paused", "focus_paused"}
            else "Tạm dừng" if state == "playing" else "Phát"
        )
        self.play_button.setEnabled(state not in {"starting", "stopping"})
        self.next_button.setEnabled(state != "stopping")
        self.stop_button.setEnabled(state not in {"idle", "error"})


class PlaybackDock(QFrame):
    play_requested, next_requested = Signal(), Signal()
    stop_requested, mini_requested = Signal(), Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("playbackDock")
        self.setMinimumHeight(128)
        row = QHBoxLayout(self)
        row.setContentsMargins(22, 13, 18, 13)
        now = QVBoxLayout()
        eyebrow = QLabel("ĐANG PHÁT")
        eyebrow.setObjectName("eyebrow")
        self.title = QLabel("Chọn một bài để bắt đầu")
        self.title.setFont(QFont(Tokens.DISPLAY, 16, QFont.Weight.DemiBold))
        self.status = QLabel("Sẵn sàng")
        self.status.setObjectName("muted")
        for widget in (eyebrow, self.title, self.status):
            now.addWidget(widget)
        row.addLayout(now, 2)
        self.runway = NoteRunway()
        row.addWidget(self.runway, 5)
        controls = QHBoxLayout()
        self.play_button, self.next_button = QPushButton("Phát"), QPushButton("Tiếp")
        self.stop_button, self.mini_button = QPushButton("Dừng"), QPushButton("Mini")
        self.play_button.setProperty("primary", True)
        self.stop_button.setProperty("danger", True)
        for button in (self.play_button, self.next_button, self.stop_button, self.mini_button):
            button.setProperty("compact", True)
            controls.addWidget(button)
        row.addLayout(controls)
        self.play_button.clicked.connect(self.play_requested)
        self.next_button.clicked.connect(self.next_requested)
        self.stop_button.clicked.connect(self.stop_requested)
        self.mini_button.clicked.connect(self.mini_requested)

    def sync(self, song: Song | None, state: str) -> None:
        if song:
            self.title.setText(song.title)
        self.status.setStyleSheet("")
        self.status.setText({
            "idle": "Sẵn sàng", "playing": "Đang phát",
            "paused": "Đang tạm dừng", "stopping": "Đang dừng",
            "countdown": "Đang đếm ngược", "starting": "Đang chuẩn bị",
            "focus_paused": "Đang chờ cửa sổ Sky", "error": "Có lỗi phát nhạc",
        }.get(state, state))
        self.play_button.setText(
            "Tiếp tục" if state in {"paused", "focus_paused"}
            else "Tạm dừng" if state == "playing" else "Phát"
        )
        self.play_button.setEnabled(state not in {"starting", "stopping"})
        self.next_button.setEnabled(state != "stopping")
        self.stop_button.setEnabled(state not in {"idle", "error"})
        self.runway.set_playing(state == "playing")


class FilterPill(QPushButton):
    def __init__(self, text: str, key: str) -> None:
        super().__init__(text)
        self.key = key
        self.setCheckable(True)
        self.setProperty("compact", True)


class LibraryPage(QWidget):
    play_requested, queue_requested = Signal(object), Signal(object)
    favorite_requested = Signal(object)

    def __init__(self, songs: list[Song]) -> None:
        super().__init__()
        self.songs = songs
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 22, 18)
        eyebrow = QLabel("THƯ VIỆN BÀI HÁT")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Thư viện")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Tìm bài, đánh dấu yêu thích hoặc đưa vào hàng chờ.")
        subtitle.setObjectName("muted")
        for widget in (eyebrow, title, subtitle):
            layout.addWidget(widget)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm theo tên bài…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Tìm bài hát")
        toolbar.addWidget(self.search, 1)
        self.filters = QButtonGroup(self)
        self.filters.setExclusive(True)
        for label, key in (("Tất cả", "all"), ("Yêu thích", "favorites")):
            pill = FilterPill(label, key)
            pill.setChecked(key == "all")
            self.filters.addButton(pill)
            toolbar.addWidget(pill)
        layout.addLayout(toolbar)
        self.list = QListWidget()
        self.list.setAccessibleName("Danh sách bài hát")
        self.list.setUniformItemSizes(True)
        layout.addWidget(self.list, 1)
        actions = QHBoxLayout()
        play = QPushButton("Phát bài đã chọn")
        play.setProperty("primary", True)
        queue, favorite = QPushButton("Thêm hàng chờ"), QPushButton("Đổi trạng thái yêu thích")
        for button in (play, queue, favorite):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.search.textChanged.connect(self.apply_filter)
        self.filters.buttonClicked.connect(self.apply_filter)
        self.list.itemDoubleClicked.connect(lambda _: self._emit(self.play_requested))
        play.clicked.connect(lambda: self._emit(self.play_requested))
        queue.clicked.connect(lambda: self._emit(self.queue_requested))
        favorite.clicked.connect(lambda: self._emit(self.favorite_requested))
        self.rebuild()

    def rebuild(self) -> None:
        selected = self.selected_song()
        self.list.clear()
        for song in self.songs:
            item = QListWidgetItem(song.title + ("  ·  Yêu thích" if song.favorite else ""))
            item.setData(Qt.ItemDataRole.UserRole, song)
            item.setToolTip(str(song.path))
            self.list.addItem(item)
            if selected and selected.path == song.path:
                self.list.setCurrentItem(item)
        self.apply_filter()

    @Slot()
    def apply_filter(self) -> None:
        needle = self.search.text().strip().casefold()
        active = self.filters.checkedButton()
        favorites_only = isinstance(active, FilterPill) and active.key == "favorites"
        visible = 0
        for index in range(self.list.count()):
            item = self.list.item(index)
            song = item.data(Qt.ItemDataRole.UserRole)
            show = needle in song.title.casefold() and (song.favorite or not favorites_only)
            item.setHidden(not show)
            visible += int(show)
        self.list.setToolTip(
            "" if visible else "Không có bài phù hợp. Hãy thử từ khóa khác hoặc bỏ bộ lọc yêu thích."
        )

    def selected_song(self) -> Song | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _emit(self, signal) -> None:
        song = self.selected_song()
        if song:
            signal.emit(song)


class QueuePanel(QWidget):
    play_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("queuePanel")
        self.setMinimumWidth(246)
        self.setMaximumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 22, 16, 14)
        eyebrow = QLabel("PHÁT TIẾP")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Hàng chờ")
        title.setFont(QFont(Tokens.DISPLAY, 19, QFont.Weight.DemiBold))
        self.hint = QLabel("Thêm bài từ thư viện.")
        self.hint.setObjectName("muted")
        self.list = QListWidget()
        self.list.setAccessibleName("Hàng chờ phát nhạc")
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        remove = QPushButton("Bỏ bài đã chọn")
        remove.setProperty("danger", True)
        for widget in (eyebrow, title, self.hint, self.list, remove):
            layout.addWidget(widget)
        layout.setStretchFactor(self.list, 1)
        self.list.itemDoubleClicked.connect(
            lambda item: self.play_requested.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        remove.clicked.connect(self._remove)

    def add_song(self, song: Song) -> None:
        item = QListWidgetItem(song.title)
        item.setData(Qt.ItemDataRole.UserRole, song)
        self.list.addItem(item)
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

    def _remove(self) -> None:
        if self.list.currentRow() >= 0:
            self.list.takeItem(self.list.currentRow())
            self._sync_hint()

    def _sync_hint(self) -> None:
        self.hint.setText(
            f"{self.list.count()} bài đang chờ" if self.list.count() else "Thêm bài từ thư viện."
        )


class HotkeysPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        eyebrow = QLabel("ĐIỀU KHIỂN")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Phím tắt")
        title.setObjectName("pageTitle")
        copy = QLabel("Chỉnh phím tắt toàn cục và các ô bài, sau đó lưu để áp dụng.")
        copy.setObjectName("muted")
        copy.setWordWrap(True)
        for widget in (eyebrow, title, copy):
            layout.addWidget(widget)
        form = QFormLayout()
        self.fields = {}
        for label, value in (("Phát / Tạm dừng", "Space"), ("Dừng", "Esc"),
                             ("Bài tiếp theo", "Ctrl+Right"), ("Chế độ mini", "Ctrl+M")):
            field = QLineEdit(value)
            field.setAccessibleName(f"Phím tắt {label}")
            self.fields[label] = field
            form.addRow(label, field)
        layout.addSpacing(18)
        layout.addLayout(form)
        self.feedback = QLabel("")
        save = QPushButton("Lưu phím tắt")
        save.setProperty("primary", True)
        save.clicked.connect(self.validate)
        layout.addWidget(self.feedback)
        layout.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

    def validate(self) -> None:
        values = [field.text().strip().casefold() for field in self.fields.values()]
        invalid = any(not value for value in values) or len(values) != len(set(values))
        self.feedback.setStyleSheet(f"color: {Tokens.DANGER if invalid else Tokens.SKY_BLUE};")
        self.feedback.setText(
            "Mỗi hành động cần một phím riêng." if invalid else "Đã kiểm tra. Chưa ghi vào cấu hình cũ."
        )


class SettingsPage(QWidget):
    reduced_motion_changed = Signal(bool)
    layout_changed = Signal(str)
    countdown_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        self.content_layout = layout
        scroll.setWidget(content)
        outer.addWidget(scroll)
        eyebrow = QLabel("TÙY CHỌN")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Cài đặt")
        title.setObjectName("pageTitle")
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        form = QFormLayout()
        self.key_layout = QComboBox()
        for key, detail in MacroPlayer.KEY_LAYOUTS.items():
            self.key_layout.addItem(detail["name"], key)
        self.countdown = QSlider(Qt.Orientation.Horizontal)
        self.countdown.setRange(0, 10)
        self.countdown.setValue(3)
        self.countdown_value = QLabel("3 giây")
        countdown_row = QHBoxLayout()
        countdown_row.addWidget(self.countdown, 1)
        countdown_row.addWidget(self.countdown_value)
        self.reduced_motion = QCheckBox("Giảm chuyển động của Note Runway")
        self.always_on_top = QCheckBox("Giữ mini player trên cùng")
        self.always_on_top.setChecked(True)
        form.addRow("Bộ phím trong game", self.key_layout)
        form.addRow("Đếm ngược", countdown_row)
        form.addRow("Chuyển động", self.reduced_motion)
        form.addRow("Mini player", self.always_on_top)
        layout.addSpacing(18)
        layout.addLayout(form)
        layout.addStretch(1)
        self.reduced_motion.toggled.connect(self.reduced_motion_changed)
        self.key_layout.currentIndexChanged.connect(
            lambda _: self.layout_changed.emit(self.key_layout.currentData())
        )
        self.countdown.valueChanged.connect(self._countdown)

    def _countdown(self, value: int) -> None:
        self.countdown_value.setText(f"{value} giây")
        self.countdown_changed.emit(value)
