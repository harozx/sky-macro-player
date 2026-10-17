"""Dialogs: sheet import preview, first-run guide, command palette, window picker."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..engine import MacroPlayer
from ..library import ImportCandidate, Song
from ..search import matches
from ..window_focus import WindowInfo, executable_name
from .theme import STYLE
from .widgets import format_duration

CONFLICT_ACTIONS = (("Đổi tên bài mới", "rename"), ("Ghi đè bài cũ", "overwrite"),
                    ("Bỏ qua bài trùng", "skip"))


class ImportDialog(QDialog):
    """Shows what each file contains before anything is copied."""

    def __init__(self, candidates: list[ImportCandidate], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nhập sheet")
        self.setStyleSheet(STYLE)
        self.resize(720, 420)
        self.candidates = candidates
        layout = QVBoxLayout(self)
        valid = [c for c in candidates if c.valid]
        heading = QLabel(f"{len(valid)}/{len(candidates)} file hợp lệ sẽ được chép vào thư viện. "
                         "File gốc không bị thay đổi.")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.table = QTableWidget(len(candidates), 4)
        self.table.setHorizontalHeaderLabels(["File", "Kết quả kiểm tra", "Nốt", "Thời lượng"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, candidate in enumerate(candidates):
            if not candidate.valid:
                status = f"Lỗi: {candidate.error}"
            elif candidate.conflict:
                status = "Hợp lệ · trùng tên với bài đã có"
            elif candidate.layered:
                status = "Hợp lệ · có lớp 2Key/3Key (chọn cách xử lý sau khi nhập)"
            else:
                status = "Hợp lệ"
            cells = (candidate.source.name, status,
                     str(candidate.note_count) if candidate.valid else "",
                     format_duration(candidate.duration_ms) if candidate.valid else "")
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, column, item)
        layout.addWidget(self.table, 1)
        conflict_row = QHBoxLayout()
        conflict_row.addWidget(QLabel("Nếu trùng tên:"))
        self.conflict = QComboBox()
        self.conflict.setAccessibleName("Cách xử lý file trùng tên")
        for label, value in CONFLICT_ACTIONS:
            self.conflict.addItem(label, value)
        conflict_row.addWidget(self.conflict)
        conflict_row.addStretch(1)
        self.conflict.setEnabled(any(c.conflict and c.valid for c in candidates))
        layout.addLayout(conflict_row)
        buttons = QDialogButtonBox()
        self.import_button = buttons.addButton(f"Nhập {len(valid)} bài",
                                               QDialogButtonBox.ButtonRole.AcceptRole)
        self.import_button.setProperty("primary", True)
        self.import_button.setEnabled(bool(valid))
        buttons.addButton("Hủy", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def conflict_action(self) -> str:
        return self.conflict.currentData()


class OnboardingWizard(QDialog):
    """Three short steps: in-game layout, focus lock, the keys that matter."""

    def __init__(self, *, layout_name: str, focus_lock: bool, stop_key: str, pause_key: str,
                 next_key: str, test_window: Callable[[], str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Thiết lập Sky Macro Player")
        self.setStyleSheet(STYLE)
        self.resize(560, 360)
        root = QVBoxLayout(self)
        self.step_label = QLabel()
        self.step_label.setObjectName("eyebrow")
        root.addWidget(self.step_label)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Bộ phím trong game")
        title.setObjectName("pageTitle")
        text = QLabel("Trong Sky, mở Cài đặt → Điều khiển để xem đàn đang dùng bộ phím nào. "
                      "Chọn đúng bộ phím để các nốt rơi vào đúng phím đàn.")
        text.setWordWrap(True)
        text.setObjectName("muted")
        self.layout_combo = QComboBox()
        self.layout_combo.setAccessibleName("Bộ phím trong game")
        for key, detail in MacroPlayer.KEY_LAYOUTS.items():
            self.layout_combo.addItem(detail["name"], key)
        self.layout_combo.setCurrentIndex(max(0, self.layout_combo.findData(layout_name)))
        for widget in (title, text, self.layout_combo):
            layout.addWidget(widget)
        layout.addStretch(1)
        self.pages.addWidget(page)

        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Giữ phím trong game")
        title.setObjectName("pageTitle")
        text = QLabel("Nên bật: nếu bạn chuyển sang cửa sổ khác, bản nhạc tự tạm dừng và không "
                      "gõ nhầm phím vào ứng dụng đó. Mở Sky rồi nhấn kiểm tra.")
        text.setWordWrap(True)
        text.setObjectName("muted")
        self.focus_lock = QCheckBox("Bật chế độ khóa vào cửa sổ game")
        self.focus_lock.setChecked(focus_lock)
        check = QPushButton("Kiểm tra cửa sổ Sky")
        check.setProperty("outline", True)
        self.check_result = QLabel("")
        self.check_result.setWordWrap(True)
        check.clicked.connect(lambda: self.check_result.setText(test_window()))
        for widget in (title, text, self.focus_lock, check, self.check_result):
            layout.addWidget(widget)
        layout.addStretch(1)
        self.pages.addWidget(page)

        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("Những phím cần nhớ")
        title.setObjectName("pageTitle")
        text = QLabel(
            f"• Dừng khẩn cấp: {stop_key.upper()}\n"
            f"• Tạm dừng / tiếp tục: {pause_key.upper()}\n"
            f"• Bài tiếp theo: {next_key.upper()}\n\n"
            "Sau khi nhấn Phát, bạn có vài giây đếm ngược để click vào game. "
            "Muốn nghe thử trước? Bật “Xem trước” ở thanh phát: ứng dụng chỉ chơi trên bàn "
            "phím ảo, không gửi phím ra ngoài. Có thể đổi phím tắt ở trang Phím tắt.")
        text.setWordWrap(True)
        for widget in (title, text):
            layout.addWidget(widget)
        layout.addStretch(1)
        self.pages.addWidget(page)

        buttons = QHBoxLayout()
        self.skip_button = QPushButton("Bỏ qua")
        self.back_button = QPushButton("Quay lại")
        self.next_button = QPushButton("Tiếp")
        self.next_button.setProperty("primary", True)
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        root.addLayout(buttons)
        self.skip_button.clicked.connect(self.reject)
        self.back_button.clicked.connect(lambda: self._go(self.pages.currentIndex() - 1))
        self.next_button.clicked.connect(self._next)
        self._go(0)

    def _go(self, index: int) -> None:
        index = max(0, min(self.pages.count() - 1, index))
        self.pages.setCurrentIndex(index)
        self.step_label.setText(f"BƯỚC {index + 1}/{self.pages.count()}")
        self.back_button.setEnabled(index > 0)
        self.next_button.setText("Hoàn tất" if index == self.pages.count() - 1 else "Tiếp")

    def _next(self) -> None:
        if self.pages.currentIndex() == self.pages.count() - 1:
            self.accept()
        else:
            self._go(self.pages.currentIndex() + 1)

    def values(self) -> dict:
        return {"keyboard_layout": self.layout_combo.currentData(),
                "focus_lock_enabled": self.focus_lock.isChecked()}


class CommandPalette(QDialog):
    """Ctrl+K: type to find a song or a command, Enter to run it."""

    song_chosen = Signal(object)

    def __init__(self, songs: list[Song], commands: list[tuple[str, Callable[[], None]]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bảng lệnh")
        self.setStyleSheet(STYLE)
        self.resize(560, 420)
        self.songs, self.commands = songs, commands
        layout = QVBoxLayout(self)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Gõ tên bài hoặc lệnh… (Enter để chạy, Esc để đóng)")
        self.input.setAccessibleName("Tìm bài hoặc lệnh")
        self.list = QListWidget()
        self.list.setAccessibleName("Kết quả")
        layout.addWidget(self.input)
        layout.addWidget(self.list, 1)
        self.input.textChanged.connect(self._refresh)
        self.input.returnPressed.connect(self._run_current)
        self.list.itemActivated.connect(lambda _: self._run_current())
        for key, step in (("Down", 1), ("Up", -1)):
            shortcut = QShortcut(QKeySequence(key), self.input)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(lambda step=step: self._move(step))
        self._refresh()

    def _refresh(self) -> None:
        query = self.input.text().strip()
        self.list.clear()
        for label, callback in self.commands:
            if matches(query, label):
                item = QListWidgetItem(f"Lệnh · {label}")
                item.setData(Qt.ItemDataRole.UserRole, ("command", callback))
                self.list.addItem(item)
        shown = 0
        for song in self.songs:
            if shown >= 50:
                break
            if query and matches(query, song.title, song.path.stem):
                suffix = "" if song.playable else "  ·  Không hỗ trợ"
                item = QListWidgetItem(f"Phát · {song.title}{suffix}")
                item.setData(Qt.ItemDataRole.UserRole, ("song", song))
                self.list.addItem(item)
                shown += 1
        if self.list.count():
            self.list.setCurrentRow(0)

    def _move(self, step: int) -> None:
        if self.list.count():
            self.list.setCurrentRow((self.list.currentRow() + step) % self.list.count())

    def _run_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        kind, payload = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if kind == "song":
            self.song_chosen.emit(payload)
        else:
            payload()


class WindowPickerDialog(QDialog):
    """Lets the user explicitly choose which game window focus lock protects."""

    def __init__(self, windows: list[WindowInfo], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Chọn cửa sổ game")
        self.setStyleSheet(STYLE)
        self.resize(560, 400)
        layout = QVBoxLayout(self)
        text = QLabel("Mở game trước, rồi chọn cửa sổ của nó. Ứng dụng sẽ nhận diện game "
                      "theo tên file chạy (.exe) mỗi lần phát.")
        text.setWordWrap(True)
        text.setObjectName("muted")
        self.list = QListWidget()
        self.list.setAccessibleName("Các cửa sổ đang mở")
        for window in windows:
            name = executable_name(window.process_path)
            item = QListWidgetItem(f"{window.title}  ·  {name}")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.list.addItem(item)
        if not windows:
            self.list.addItem("Không tìm thấy cửa sổ nào có thể chọn.")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Chọn")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Hủy")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        for widget in (text, self.list, buttons):
            layout.addWidget(widget)

    def selected_exe(self) -> str | None:
        item = self.list.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return value or None
