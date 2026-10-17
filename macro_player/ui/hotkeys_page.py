"""Hotkey editor: record shortcuts by pressing them, validate before applying."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..domain import Settings
from ..hotkeys import RESERVED, canonical_hotkey, conflicts_with_music_keys
from ..i18n import tr
from ..library import Song
from .theme import Tokens
from .widgets import HotkeyEdit


class EditableHotkeysPage(QWidget):
    save_requested = Signal(object)

    RESERVED = RESERVED

    def __init__(self, settings: Settings, songs: list[Song]) -> None:
        super().__init__()
        self.music_keys: tuple[str, ...] = ()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        eyebrow = QLabel(tr("ĐIỀU KHIỂN"))
        eyebrow.setObjectName("eyebrow")
        title = QLabel(tr("Phím tắt"))
        title.setObjectName("pageTitle")
        copy = QLabel(
            tr("Bấm vào một ô rồi nhấn tổ hợp phím muốn dùng. Phím tắt toàn cục hoạt động cả "
            "khi đang ở trong game. Nhấn “Lưu và áp dụng” để bật."))
        copy.setObjectName("muted")
        copy.setWordWrap(True)
        for widget in (eyebrow, title, copy):
            layout.addWidget(widget)
        layout.addSpacing(14)
        form = QFormLayout()
        self.action_fields = {
            "pause": HotkeyEdit(settings.pause_hotkey),
            "stop": HotkeyEdit(settings.hotkeys.get("stop", "F10")),
            "next": HotkeyEdit(settings.hotkeys.get("next", "F11")),
        }
        for key, label in (("pause", tr("Tạm dừng / tiếp tục")), ("stop", tr("Dừng")),
                           ("next", tr("Bài tiếp theo"))):
            self.action_fields[key].setAccessibleName(tr("Phím tắt {label}").format(label=label))
            form.addRow(label, self.action_fields[key])
        self.slot_fields: list[tuple[HotkeyEdit, QComboBox]] = []
        for index, key in enumerate(settings.hotkey_keys):
            shortcut = HotkeyEdit(key)
            shortcut.setAccessibleName(tr("Phím tắt ô bài {0}").format(index + 1))
            song = QComboBox()
            song.setAccessibleName(tr("Bài cho ô {0}").format(index + 1))
            selected = settings.song_slots[index] if index < len(settings.song_slots) else None
            self._fill_songs(song, songs, selected)
            row = QHBoxLayout()
            row.addWidget(shortcut, 1)
            row.addWidget(song, 3)
            form.addRow(tr("Ô bài {0}").format(index + 1), row)
            self.slot_fields.append((shortcut, song))
        layout.addLayout(form)
        local = QLabel(
            tr("Phím tắt trong ứng dụng: Space phát/tạm dừng · Esc dừng · Ctrl+→ bài tiếp · "
            "Ctrl+M mini · Ctrl+F tìm · Ctrl+K bảng lệnh · Enter phát bài chọn · "
            "Ctrl+Enter thêm hàng chờ · Ctrl+O nhập sheet"))
        local.setObjectName("muted")
        local.setWordWrap(True)
        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        save = QPushButton(tr("Lưu và áp dụng"))
        save.setProperty("primary", True)
        save.setMinimumHeight(40)
        save.clicked.connect(self._save)
        layout.addSpacing(10)
        layout.addWidget(local)
        layout.addWidget(self.feedback)
        layout.addWidget(save)
        layout.addStretch(1)

    @staticmethod
    def _reference(song: Song) -> str:
        return song.relative or song.path.as_posix()

    def _fill_songs(self, combo: QComboBox, songs: list[Song], selected: str | None) -> None:
        combo.clear()
        combo.addItem(tr("Chưa gán"), None)
        references = [(song, self._reference(song)) for song in songs]
        for song, reference in references:
            combo.addItem(song.title, reference)
        if not selected:
            return
        normalized = selected.replace("\\", "/")
        match = combo.findData(normalized)
        if match < 0:
            legacy = [row for row, (_, reference) in enumerate(references, start=1)
                      if Path(reference).name.casefold() == Path(normalized).name.casefold()]
            if len(legacy) == 1:
                match = legacy[0]
        combo.setCurrentIndex(max(0, match))

    def update_songs(self, songs: list[Song]) -> None:
        for _, combo in self.slot_fields:
            self._fill_songs(combo, songs, combo.currentData())

    def set_music_keys(self, keys) -> None:
        self.music_keys = tuple(keys)

    def values(self) -> dict:
        return {
            "pause": self.action_fields["pause"].text().strip(),
            "stop": self.action_fields["stop"].text().strip(),
            "next": self.action_fields["next"].text().strip(),
            "slot_keys": tuple(field.text().strip() for field, _ in self.slot_fields),
            "song_slots": tuple(combo.currentData() for _, combo in self.slot_fields),
        }

    def validate_values(self) -> tuple[bool, str]:
        values = self.values()
        raw = [values["pause"], values["stop"], values["next"], *values["slot_keys"]]
        if any(not key for key in raw):
            return False, tr("Mỗi hành động và ô bài cần một phím tắt.")
        canonical = [canonical_hotkey(key) for key in raw]
        if len(canonical) != len(set(canonical)):
            return False, tr("Một phím đang được dùng cho nhiều hành động.")
        if any(key in self.RESERVED for key in canonical):
            return False, tr("Một phím được Windows giữ riêng. Hãy chọn tổ hợp khác.")
        clashes = [key for key in raw if conflicts_with_music_keys(key, self.music_keys)]
        if clashes:
            return False, (tr("Phím {0} là phím chơi nhạc trong game; "
                           "dùng nó làm phím tắt sẽ bị kích hoạt khi bài đang phát.").format(
                               ', '.join(clashes)))
        return True, ""

    def show_feedback(self, message: str, success: bool) -> None:
        self.feedback.setStyleSheet(f"color: {Tokens.SKY_BLUE if success else Tokens.DANGER};")
        self.feedback.setText(message)

    def _save(self) -> None:
        valid, message = self.validate_values()
        if not valid:
            self.show_feedback(message, False)
            return
        self.save_requested.emit(self.values())
