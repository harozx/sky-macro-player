"""Library page: accent-insensitive search, sort, filters and song details."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..i18n import N_, tr
from ..library import LAYER_POLICY_LABELS, Song
from ..search import fold_text, matches
from .widgets import format_duration

SORT_OPTIONS = (
    (N_("Tên A–Z"), "title"),
    (N_("Tên Z–A"), "title_desc"),
    (N_("Ngắn nhất"), "shortest"),
    (N_("Dài nhất"), "longest"),
    (N_("Mới thêm"), "newest"),
    (N_("Nghe nhiều"), "most_played"),
    (N_("Nghe gần đây"), "recent"),
)
FILTERS = ((N_("Tất cả"), "all"), (N_("Yêu thích"), "favorites"),
           (N_("Phát được"), "playable"), (N_("Gần đây"), "recent"))


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
    if key == "most_played":
        return sorted(songs, key=lambda song: (-song.play_count, by_title(song)))
    if key == "recent":
        return sorted(songs, key=lambda song: (-song.last_played, by_title(song)))
    return sorted(songs, key=by_title)


class FilterPill(QPushButton):
    def __init__(self, text: str, key: str) -> None:
        super().__init__(text)
        self.key = key
        self.setCheckable(True)
        self.setProperty("compact", True)
        self.setAccessibleName(tr("Lọc: {text}").format(text=text))


class LibraryPage(QWidget):
    play_requested, queue_requested = Signal(object), Signal(object)
    favorite_requested = Signal(object)
    play_all_requested = Signal(list, bool)
    import_requested = Signal()
    undo_import_requested = Signal()
    text_import_requested = Signal()
    batch_requested = Signal()
    edit_requested = Signal(object)
    layer_policy_changed = Signal(object, object)

    def __init__(self, songs: list[Song]) -> None:
        super().__init__()
        self.songs = songs
        self.policies: dict[str, str | None] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 22, 18)
        eyebrow = QLabel(tr("THƯ VIỆN BÀI HÁT"))
        eyebrow.setObjectName("eyebrow")
        header = QHBoxLayout()
        title = QLabel(tr("Thư viện"))
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.import_button = QPushButton(tr("Nhập sheet…"))
        self.import_button.setProperty("outline", True)
        self.import_button.setToolTip(tr("Chọn file .txt/.json hoặc kéo-thả file vào cửa sổ"))
        self.undo_import_button = QPushButton()
        self.undo_import_button.setProperty("outline", True)
        self.undo_import_button.setAccessibleName(tr("Hoàn tác lần nhập sheet vừa rồi"))
        self.undo_import_button.hide()
        self.tools_button = QPushButton(tr("Công cụ"))
        self.tools_button.setProperty("outline", True)
        self.tools_menu = QMenu(self.tools_button)
        self.text_import_action = self.tools_menu.addAction(tr("Nhập sheet chữ…"))
        self.batch_action = self.tools_menu.addAction(tr("Xử lý cả thư mục sheet…"))
        self.tools_button.setMenu(self.tools_menu)
        header.addWidget(self.undo_import_button)
        header.addWidget(self.tools_button)
        header.addWidget(self.import_button)
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        self.eyebrow = eyebrow
        layout.addWidget(eyebrow)
        layout.addLayout(header)
        layout.addWidget(self.summary)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Tìm theo tên bài, không cần gõ dấu… (Ctrl+F)"))
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName(tr("Tìm bài hát"))
        toolbar.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.setAccessibleName(tr("Sắp xếp danh sách bài"))
        for label, key in SORT_OPTIONS:
            self.sort.addItem(tr(label), key)
        toolbar.addWidget(self.sort)
        layout.addLayout(toolbar)
        pills = QHBoxLayout()
        self.filters = QButtonGroup(self)
        self.filters.setExclusive(True)
        for label, key in FILTERS:
            pill = FilterPill(tr(label), key)
            pill.setChecked(key == "all")
            self.filters.addButton(pill)
            pills.addWidget(pill)
        pills.addStretch(1)
        self.result_count = QLabel()
        self.result_count.setObjectName("muted")
        pills.addWidget(self.result_count)
        layout.addLayout(pills)
        self.list = QListWidget()
        self.list.setAccessibleName(
            tr("Danh sách bài hát. Enter để phát, Ctrl+Enter để thêm hàng chờ"))
        self.list.setUniformItemSizes(True)
        layout.addWidget(self.list, 1)
        self.empty_state = QLabel()
        self.empty_state.setObjectName("muted")
        self.empty_state.setWordWrap(True)
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.hide()
        layout.addWidget(self.empty_state, 1)

        self.detail = QFrame()
        self.detail.setObjectName("detailPanel")
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(12, 8, 12, 8)
        self.detail_title = QLabel()
        self.detail_title.setObjectName("sectionTitle")
        self.detail_meta = QLabel()
        self.detail_meta.setObjectName("muted")
        self.detail_meta.setWordWrap(True)
        policy_row = QHBoxLayout()
        self.policy_label = QLabel(tr("Bài có lớp 2Key/3Key:"))
        self.policy = QComboBox()
        self.policy.setAccessibleName(tr("Cách xử lý lớp 2Key/3Key"))
        for value, label in LAYER_POLICY_LABELS.items():
            self.policy.addItem(tr(label), value or "")
        policy_row.addWidget(self.policy_label)
        policy_row.addWidget(self.policy, 1)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addLayout(policy_row)
        layout.addWidget(self.detail)

        actions = QHBoxLayout()
        play = QPushButton(tr("Phát bài đã chọn"))
        play.setProperty("primary", True)
        queue, favorite = QPushButton(
            tr("Thêm hàng chờ")), QPushButton(tr("Đổi trạng thái yêu thích"))
        play.setToolTip("Enter")
        queue.setToolTip("Ctrl+Enter")
        self.edit_button = QPushButton(tr("Chỉnh sheet…"))
        self.edit_button.setToolTip(tr("Gộp lớp, cắt đoạn, chỉnh nhịp, dịch tông, đổi tempo; "
                                       "lưu thành bản mới"))
        for button in (play, queue, favorite, self.edit_button):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        list_actions = QHBoxLayout()
        self.play_all_button = QPushButton(tr("Phát tất cả"))
        self.shuffle_button = QPushButton(tr("Trộn bài"))
        self.play_all_button.setToolTip(
            tr("Thay hàng chờ bằng các bài đang hiển thị rồi phát từ đầu."))
        self.shuffle_button.setToolTip(
            tr("Thay hàng chờ bằng các bài đang hiển thị theo thứ tự ngẫu nhiên.")
        )
        for button in (self.play_all_button, self.shuffle_button):
            list_actions.addWidget(button)
        list_actions.addStretch(1)
        layout.addLayout(list_actions)

        self.search.textChanged.connect(self.apply_filter)
        self.search.returnPressed.connect(self._focus_first_result)
        self.filters.buttonClicked.connect(self.apply_filter)
        self.sort.currentIndexChanged.connect(self.rebuild)
        self.list.itemDoubleClicked.connect(lambda _: self._emit(self.play_requested))
        self.list.currentItemChanged.connect(lambda *_: self._show_details())
        play.clicked.connect(lambda: self._emit(self.play_requested))
        queue.clicked.connect(lambda: self._emit(self.queue_requested))
        favorite.clicked.connect(lambda: self._emit(self.favorite_requested))
        self.edit_button.clicked.connect(lambda: self._emit(self.edit_requested))
        self.import_button.clicked.connect(self.import_requested)
        self.undo_import_button.clicked.connect(self.undo_import_requested)
        self.text_import_action.triggered.connect(self.text_import_requested)
        self.batch_action.triggered.connect(self.batch_requested)
        self.play_all_button.clicked.connect(
            lambda: self.play_all_requested.emit(self.visible_songs(), False))
        self.shuffle_button.clicked.connect(
            lambda: self.play_all_requested.emit(self.visible_songs(), True))
        self.policy.activated.connect(self._policy_activated)
        for sequence, signal in (("Return", self.play_requested), ("Enter", self.play_requested),
                                 ("Ctrl+Return", self.queue_requested),
                                 ("Ctrl+Enter", self.queue_requested)):
            shortcut = QShortcut(QKeySequence(sequence), self.list)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(lambda signal=signal: self._emit(signal))
        self.rebuild()

    @staticmethod
    def item_text(song: Song) -> str:
        parts = [song.title]
        if song.duration_ms:
            parts.append(format_duration(song.duration_ms))
        if song.favorite:
            parts.append(tr("Yêu thích"))
        if not song.playable:
            parts.append(tr("Không hỗ trợ"))
        return "  ·  ".join(parts)

    def show_undo_import(self, count: int) -> None:
        self.undo_import_button.setText(tr("Hoàn tác nhập ({count})").format(count=count))
        self.undo_import_button.setVisible(count > 0)

    def set_songs(self, songs: list[Song]) -> None:
        self.songs = songs
        self.rebuild()

    @Slot()
    def rebuild(self) -> None:
        selected = self.selected_song()
        self.list.clear()
        for song in sort_songs(list(self.songs), self.sort.currentData() or "title"):
            item = QListWidgetItem(self.item_text(song))
            item.setData(Qt.ItemDataRole.UserRole, song)
            item.setToolTip(song.identity)
            self.list.addItem(item)
            if selected and selected.path == song.path:
                self.list.setCurrentItem(item)
        playable = sum(song.playable for song in self.songs)
        self.summary.setText(
            tr("{0} bài · {playable} phát được. "
            "Tìm bài, đánh dấu yêu thích hoặc đưa vào hàng chờ.").format(
                len(self.songs), playable=playable)
        )
        self.apply_filter()
        self._show_details()

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
                and (mode != "recent" or song.last_played > 0)
            )
            item.setHidden(not show)
            visible += int(show)
        total = self.list.count()
        self.result_count.setText(tr("Hiển thị {visible}/{total}").format(
            visible=visible, total=total))
        if not total:
            message = (tr("Thư viện đang trống. Nhấn “Nhập sheet…” hoặc kéo-thả file "
                       ".txt/.json vào cửa sổ để thêm bài."))
        elif not visible and query:
            message = (tr("Không có bài nào khớp “{query}”. "
                       "Hãy thử từ khóa ngắn hơn hoặc chọn bộ lọc Tất cả.").format(query=query))
        elif not visible:
            message = {
                "favorites": tr("Chưa có bài yêu thích. Chọn một bài rồi nhấn "
                             "“Đổi trạng thái yêu thích”."),
                "recent": tr("Chưa phát bài nào. Các bài đã phát sẽ hiện ở đây."),
            }.get(mode, tr("Không có bài phù hợp với bộ lọc này."))
        else:
            message = ""
        self.empty_state.setText(message)
        self.empty_state.setVisible(bool(message))
        self.list.setVisible(not message)
        current = self.list.currentItem()
        if current is not None and current.isHidden():
            self.list.setCurrentItem(None)  # type: ignore[call-overload]
            self._focus_first_result(move_focus=False)
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

    def select_song(self, song: Song) -> None:
        for index in range(self.list.count()):
            if self.list.item(index).data(Qt.ItemDataRole.UserRole).path == song.path:
                self.list.setCurrentRow(index)
                return

    def _focus_first_result(self, move_focus: bool = True) -> None:
        for index in range(self.list.count()):
            if not self.list.item(index).isHidden():
                self.list.setCurrentRow(index)
                if move_focus:
                    self.list.setFocus()
                return
        self._show_details()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        roomy = self.height() >= 470
        self.eyebrow.setVisible(roomy)
        self.summary.setVisible(roomy)
        self._show_details()

    def _show_details(self) -> None:
        song = self.selected_song()
        self.detail.setVisible(song is not None and self.height() >= 520)
        if song is None:
            return
        self.detail_title.setText(song.title)
        parts = []
        if song.duration_ms:
            parts.append(format_duration(song.duration_ms))
        if song.note_count:
            parts.append(tr("{note_count} nốt").format(note_count=song.note_count))
            parts.append(tr("{density:.1f} nốt/giây · {difficulty}").format(
                density=song.density, difficulty=song.difficulty))
        if song.play_count:
            parts.append(tr("đã phát {play_count} lần").format(play_count=song.play_count))
        if not song.playable:
            parts.append(tr("chưa phát được với bộ phím/lựa chọn hiện tại"))
        self.detail_meta.setText(" · ".join(parts) or tr("Sheet chưa đọc được."))
        policy = self.policies.get(song.identity)
        self.policy_label.setVisible(song.layered)
        self.policy.setVisible(song.layered)
        self.policy.setCurrentIndex(max(0, self.policy.findData(policy or "")))

    def _policy_activated(self, index: int) -> None:
        song = self.selected_song()
        if song is not None:
            self.layer_policy_changed.emit(song, self.policy.itemData(index) or None)

    def _emit(self, signal) -> None:
        song = self.selected_song()
        if song:
            signal.emit(song)
