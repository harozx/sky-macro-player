"""Compact always-on-top overlay that keeps the essential controls."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from ..library import Song
from .theme import STYLE
from .widgets import format_duration

STATE_LABELS = {
    "idle": "Sẵn sàng",
    "countdown": "Đang đếm ngược",
    "starting": "Đang chuẩn bị",
    "playing": "Đang phát",
    "paused": "Đã tạm dừng",
    "focus_paused": "Đang chờ cửa sổ Sky",
    "stopping": "Đang dừng an toàn",
    "error": "Có lỗi phát nhạc",
}


def play_label(state: str) -> str:
    if state in {"paused", "focus_paused"}:
        return "Tiếp tục"
    return "Tạm dừng" if state == "playing" else "Phát"


def clamp_to_screens(position: QPoint, size) -> QPoint:
    """Keep a remembered position on a screen that still exists."""
    screens = QGuiApplication.screens()
    for screen in screens:
        area = screen.availableGeometry()
        if area.contains(position):
            x = min(max(position.x(), area.left()), area.right() - size.width())
            y = min(max(position.y(), area.top()), area.bottom() - size.height())
            return QPoint(max(area.left(), x), max(area.top(), y))
    primary = QGuiApplication.primaryScreen()
    if primary is None:
        return position
    area = primary.availableGeometry()
    return QPoint(area.right() - size.width() - 24, area.top() + 24)


class MiniOverlay(QWidget):
    play_requested, next_requested, stop_requested = Signal(), Signal(), Signal()
    expand_requested, pin_changed = Signal(), Signal(bool)
    position_changed = Signal(int, int)

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Sky Macro Player — Mini")
        self.setObjectName("appRoot")
        self.setMinimumSize(420, 112)
        self.resize(500, 116)
        self.setMaximumHeight(150)
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)
        top = QHBoxLayout()
        self.title = QLabel("Chưa chọn bài")
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title.setStyleSheet("font-weight: 600;")
        self.status = QLabel("Sẵn sàng")
        self.status.setObjectName("muted")
        top.addWidget(self.title, 1)
        top.addWidget(self.status)
        outer.addLayout(top)
        bottom = QHBoxLayout()
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setObjectName("eyebrow")
        self.time_label.setMinimumWidth(84)
        bottom.addWidget(self.time_label)
        bottom.addStretch(1)
        self.play_button = QPushButton("Phát")
        self.play_button.setProperty("primary", True)
        self.next_button, self.stop_button = QPushButton("Tiếp"), QPushButton("Dừng")
        self.pin_button, self.expand_button = QPushButton("Ghim"), QPushButton("Mở rộng")
        self.pin_button.setCheckable(True)
        self.pin_button.setChecked(True)
        self.stop_button.setProperty("danger", True)
        for button in (self.play_button, self.next_button, self.stop_button,
                       self.pin_button, self.expand_button):
            button.setProperty("compact", True)
            button.setMinimumSize(52, 44)
            bottom.addWidget(button)
        outer.addLayout(bottom)
        self.play_button.setAccessibleName("Phát hoặc tạm dừng")
        self.next_button.setAccessibleName("Phát bài tiếp theo")
        self.stop_button.setAccessibleName("Dừng phát nhạc")
        self.pin_button.setAccessibleName("Ghim mini player trên cùng")
        self.expand_button.setAccessibleName("Mở cửa sổ đầy đủ")
        self.play_button.clicked.connect(self.play_requested)
        self.next_button.clicked.connect(self.next_requested)
        self.stop_button.clicked.connect(self.stop_requested)
        self.pin_button.toggled.connect(self.pin_changed)
        self.expand_button.clicked.connect(self.expand_requested)
        self._full_title = "Chưa chọn bài"

    def set_progress(self, elapsed: int, duration: int) -> None:
        self.time_label.setText(f"{format_duration(elapsed)} / {format_duration(duration)}")

    def _elide_title(self) -> None:
        metrics = QFontMetrics(self.title.font())
        self.title.setText(metrics.elidedText(
            self._full_title, Qt.TextElideMode.ElideRight, max(60, self.title.width())))

    def sync(self, song: Song | None, state: str, status: str | None = None) -> None:
        self._full_title = song.title if song else "Chưa chọn bài"
        self.title.setToolTip(song.title if song else "")
        self._elide_title()
        self.status.setText(status or STATE_LABELS.get(state, state))
        self.play_button.setText(play_label(state))
        self.play_button.setEnabled(state not in {"starting", "stopping"})
        self.next_button.setEnabled(state != "stopping")
        self.stop_button.setEnabled(state not in {"idle", "error"})

    def restore_position(self, position: tuple[int, int] | None) -> None:
        if position is not None:
            self.move(clamp_to_screens(QPoint(*position), self.size()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide_title()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self.isVisible():
            self.position_changed.emit(self.x(), self.y())
