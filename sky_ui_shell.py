"""Application shell for the Sky Instrument Console."""

from __future__ import annotations

import random
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
from macro_player.search import fold_text, matches
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


def format_duration(milliseconds: int) -> str:
    seconds = max(0, int(milliseconds) // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


SORT_OPTIONS = (
    ("Tên A–Z", "title"),
    ("Tên Z–A", "title_desc"),
    ("Ngắn nhất", "shortest"),
    ("Dài nhất", "longest"),
    ("Mới thêm", "newest"),
)


def sort_songs(songs: list[Song], key: str) -> list[Song]:
    def by_title(song: Song) -> str:
        return fold_text(song.title)

    if key == "title_desc":
        return sorted(songs, key=by_title, reverse=True)
    if key == "shortest":
        return sorted(songs, key=lambda song: (song.duration_ms, by_title(song)))
    if key == "longest":
        return sorted(songs, key=lambda song: (-song.duration_ms, by_title(song)))
    if key == "newest":
        return sorted(songs, key=lambda song: (-song.added_at, by_title(song)))
    return sorted(songs, key=by_title)


class LibraryPage(QWidget):
    play_requested, queue_requested = Signal(object), Signal(object)
    favorite_requested = Signal(object)
    play_all_requested = Signal(list, bool)

    def __init__(self, songs: list[Song]) -> None:
        super().__init__()
        self.songs = songs
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 22, 18)
        eyebrow = QLabel("THƯ VIỆN BÀI HÁT")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Thư viện")
        title.setObjectName("pageTitle")
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        for widget in (eyebrow, title, self.summary):
            layout.addWidget(widget)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm theo tên bài, không cần gõ dấu…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Tìm bài hát")
        toolbar.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.setAccessibleName("Sắp xếp danh sách bài")
        for label, key in SORT_OPTIONS:
            self.sort.addItem(label, key)
        toolbar.addWidget(self.sort)
        layout.addLayout(toolbar)
        pills = QHBoxLayout()
        self.filters = QButtonGroup(self)
        self.filters.setExclusive(True)
        for label, key in (("Tất cả", "all"), ("Yêu thích", "favorites"),
                           ("Phát được", "playable")):
            pill = FilterPill(label, key)
            pill.setChecked(key == "all")
            pill.setAccessibleName(f"Lọc: {label}")
            self.filters.addButton(pill)
            pills.addWidget(pill)
        pills.addStretch(1)
        self.result_count = QLabel()
        self.result_count.setObjectName("muted")
        pills.addWidget(self.result_count)
        layout.addLayout(pills)
        self.list = QListWidget()
        self.list.setAccessibleName("Danh sách bài hát")
        self.list.setUniformItemSizes(True)
        layout.addWidget(self.list, 1)
        self.empty_state = QLabel()
        self.empty_state.setObjectName("muted")
        self.empty_state.setWordWrap(True)
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()
        layout.addWidget(self.empty_state, 1)
        actions = QHBoxLayout()
        play = QPushButton("Phát bài đã chọn")
        play.setProperty("primary", True)
        queue, favorite = QPushButton("Thêm hàng chờ"), QPushButton("Đổi trạng thái yêu thích")
        self.play_all_button = QPushButton("Phát tất cả")
        self.shuffle_button = QPushButton("Trộn bài")
        self.play_all_button.setToolTip("Thay hàng chờ bằng các bài đang hiển thị rồi phát từ đầu.")
        self.shuffle_button.setToolTip("Thay hàng chờ bằng các bài đang hiển thị theo thứ tự ngẫu nhiên.")
        for button in (play, queue, favorite):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        list_actions = QHBoxLayout()
        for button in (self.play_all_button, self.shuffle_button):
            list_actions.addWidget(button)
        list_actions.addStretch(1)
        layout.addLayout(list_actions)
        self.search.textChanged.connect(self.apply_filter)
        self.filters.buttonClicked.connect(self.apply_filter)
        self.sort.currentIndexChanged.connect(self.rebuild)
        self.list.itemDoubleClicked.connect(lambda _: self._emit(self.play_requested))
        play.clicked.connect(lambda: self._emit(self.play_requested))
        queue.clicked.connect(lambda: self._emit(self.queue_requested))
        favorite.clicked.connect(lambda: self._emit(self.favorite_requested))
        self.play_all_button.clicked.connect(
            lambda: self.play_all_requested.emit(self.visible_songs(), False))
        self.shuffle_button.clicked.connect(
            lambda: self.play_all_requested.emit(self.visible_songs(), True))
        self.rebuild()

    @staticmethod
    def item_text(song: Song) -> str:
        parts = [song.title]
        if song.duration_ms:
            parts.append(format_duration(song.duration_ms))
        if song.favorite:
            parts.append("Yêu thích")
        if not song.playable:
            parts.append("Không hỗ trợ")
        return "  ·  ".join(parts)

    @Slot()
    def rebuild(self) -> None:
        selected = self.selected_song()
        self.list.clear()
        for song in sort_songs(list(self.songs), self.sort.currentData() or "title"):
            item = QListWidgetItem(self.item_text(song))
            item.setData(Qt.ItemDataRole.UserRole, song)
            details = [str(song.path)]
            if song.note_count:
                details.append(f"{song.note_count} nốt")
            if not song.playable:
                details.append("Sheet dùng phím chưa hỗ trợ; bài này sẽ bị chặn trước khi phát.")
            item.setToolTip("\n".join(details))
            self.list.addItem(item)
            if selected and selected.path == song.path:
                self.list.setCurrentItem(item)
        playable = sum(song.playable for song in self.songs)
        self.summary.setText(
            f"{len(self.songs)} bài · {playable} phát được. "
            "Tìm bài, đánh dấu yêu thích hoặc đưa vào hàng chờ."
        )
        self.apply_filter()

    @Slot()
    def apply_filter(self) -> None:
        query = self.search.text().strip()
        active = self.filters.checkedButton()
        mode = active.key if isinstance(active, FilterPill) else "all"
        visible = 0
        for index in range(self.list.count()):
            item = self.list.item(index)
            song = item.data(Qt.ItemDataRole.UserRole)
            show = (
                matches(query, song.title, song.path.stem)
                and (mode != "favorites" or song.favorite)
                and (mode != "playable" or song.playable)
            )
            item.setHidden(not show)
            visible += int(show)
        total = self.list.count()
        self.result_count.setText(f"Hiển thị {visible}/{total}")
        if not total:
            message = ("Thư viện đang trống. Chép file sheet .txt hoặc .json vào "
                       "thư mục sheets rồi mở lại ứng dụng.")
        elif not visible and query:
            message = (f"Không có bài nào khớp “{query}”. "
                       "Hãy thử từ khóa ngắn hơn hoặc chọn bộ lọc Tất cả.")
        elif not visible:
            message = ("Chưa có bài nào trong bộ lọc này. "
                       "Nhấn “Đổi trạng thái yêu thích” để thêm bài vào Yêu thích."
                       if mode == "favorites" else "Không có bài phù hợp với bộ lọc này.")
        else:
            message = ""
        self.empty_state.setText(message)
        self.empty_state.setVisible(bool(message))
        self.list.setVisible(not message)
        has_playable = any(song.playable for song in self.visible_songs())
        self.play_all_button.setEnabled(has_playable)
        self.shuffle_button.setEnabled(has_playable)

    def visible_songs(self) -> list[Song]:
        return [
            self.list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.list.count())
            if not self.list.item(index).isHidden()
        ]

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
        self.hint.setWordWrap(True)
        self.list = QListWidget()
        self.list.setAccessibleName("Hàng chờ phát nhạc")
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.repeat_mode = "off"
        self.repeat_button = QPushButton()
        self.repeat_button.setAccessibleName("Đổi chế độ lặp")
        self.repeat_button.setToolTip(
            "Tắt → Lặp hàng chờ → Lặp một bài. Dừng luôn kết thúc việc lặp.")
        self._sync_repeat()
        tools = QHBoxLayout()
        self.shuffle_button = QPushButton("Trộn")
        self.shuffle_button.setToolTip("Xáo trộn thứ tự các bài đang chờ.")
        self.clear_button = QPushButton("Xóa hết")
        for button in (self.shuffle_button, self.clear_button):
            button.setProperty("compact", True)
            tools.addWidget(button)
        self.undo_button = QPushButton("Hoàn tác")
        self.undo_button.setAccessibleName("Hoàn tác thay đổi hàng chờ")
        self.undo_button.hide()
        remove = QPushButton("Bỏ bài đã chọn")
        remove.setProperty("danger", True)
        for widget in (eyebrow, title, self.hint, self.repeat_button):
            layout.addWidget(widget)
        layout.addLayout(tools)
        for widget in (self.list, self.undo_button, remove):
            layout.addWidget(widget)
        layout.setStretchFactor(self.list, 1)
        self.list.itemDoubleClicked.connect(
            lambda item: self.play_requested.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        remove.clicked.connect(self._remove)
        self.repeat_button.clicked.connect(self.cycle_repeat)
        self.shuffle_button.clicked.connect(lambda: self.shuffle())
        self.clear_button.clicked.connect(self.clear)
        self.undo_button.clicked.connect(self.undo)
        self._undo_snapshot: list[Song] | None = None

    REPEAT_LABELS = {"off": "Lặp: Tắt", "all": "Lặp: Hàng chờ", "one": "Lặp: Một bài"}

    def _sync_repeat(self) -> None:
        self.repeat_button.setText(self.REPEAT_LABELS[self.repeat_mode])

    @Slot()
    def cycle_repeat(self) -> None:
        order = ("off", "all", "one")
        self.set_repeat_mode(order[(order.index(self.repeat_mode) + 1) % len(order)])

    def set_repeat_mode(self, mode: str) -> None:
        if mode not in self.REPEAT_LABELS:
            raise ValueError(f"Chế độ lặp không hợp lệ: {mode}")
        self.repeat_mode = mode
        self._sync_repeat()

    def songs(self) -> list[Song]:
        return [self.list.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(self.list.count())]

    def _set_songs(self, songs: list[Song]) -> None:
        self.list.clear()
        for song in songs:
            item = QListWidgetItem(song.title)
            item.setData(Qt.ItemDataRole.UserRole, song)
            self.list.addItem(item)
        self._sync_hint()

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
