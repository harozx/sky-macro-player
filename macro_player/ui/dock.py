"""Playback dock that stays visible on every page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
)

from ..library import Song
from .mini import STATE_LABELS, play_label
from .theme import Tokens
from .widgets import NoteRunway

SPEEDS = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5)


class PlaybackDock(QFrame):
    play_requested, next_requested = Signal(), Signal()
    stop_requested, mini_requested = Signal(), Signal()
    speed_changed = Signal(float)
    set_a_requested, set_b_requested, clear_loop_requested = Signal(), Signal(), Signal()
    preview_toggled, keyboard_toggled = Signal(bool), Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("playbackDock")
        self.setMinimumHeight(136)
        row = QHBoxLayout(self)
        row.setContentsMargins(22, 12, 18, 12)
        now = QVBoxLayout()
        eyebrow = QLabel("ĐANG PHÁT")
        eyebrow.setObjectName("eyebrow")
        self.title = QLabel("Chọn một bài để bắt đầu")
        self.title.setFont(QFont(Tokens.DISPLAY, 16, QFont.Weight.DemiBold))
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title.setMinimumWidth(140)
        self.status = QLabel("Sẵn sàng")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        for widget in (eyebrow, self.title, self.status):
            now.addWidget(widget)
        now.addStretch(1)
        row.addLayout(now, 2)

        center = QVBoxLayout()
        self.runway = NoteRunway()
        center.addWidget(self.runway)
        tools = QHBoxLayout()
        tools.setSpacing(4)
        speed_label = QLabel("Tốc độ")
        speed_label.setObjectName("muted")
        self.speed = QComboBox()
        self.speed.setAccessibleName("Tốc độ phát")
        for value in SPEEDS:
            self.speed.addItem(f"{value:.1f}×", value)
        self.speed.setCurrentIndex(SPEEDS.index(1.0))
        self.a_button, self.b_button = QPushButton("A"), QPushButton("B")
        self.clear_loop_button = QPushButton("Bỏ A–B")
        self.a_button.setToolTip("Đặt điểm A của đoạn lặp tại vị trí hiện tại")
        self.b_button.setToolTip("Đặt điểm B; khi có cả A và B, bài lặp đoạn A–B cho tới khi Dừng")
        self.a_button.setAccessibleName("Đặt điểm A")
        self.b_button.setAccessibleName("Đặt điểm B")
        self.preview_button = QPushButton("Xem trước")
        self.preview_button.setCheckable(True)
        self.preview_button.setToolTip(
            "Phát trên bàn phím ảo trong ứng dụng, không gửi phím nào ra game.")
        self.keyboard_button = QPushButton("Bàn phím")
        self.keyboard_button.setCheckable(True)
        self.keyboard_button.setToolTip("Hiện lưới 15 phím sáng theo nốt đang phát")
        self.speed_label = speed_label
        tools.addWidget(speed_label)
        tools.addWidget(self.speed)
        for button in (self.a_button, self.b_button, self.clear_loop_button,
                       self.preview_button, self.keyboard_button):
            button.setProperty("compact", True)
            tools.addWidget(button)
        tools.addStretch(1)
        center.addLayout(tools)
        row.addLayout(center, 5)

        controls = QHBoxLayout()
        self.play_button, self.next_button = QPushButton("Phát"), QPushButton("Tiếp")
        self.stop_button, self.mini_button = QPushButton("Dừng"), QPushButton("Thu nhỏ")
        self.play_button.setProperty("primary", True)
        self.stop_button.setProperty("danger", True)
        self.play_button.setAccessibleName("Phát hoặc tạm dừng (Space)")
        self.next_button.setAccessibleName("Bài tiếp theo (Ctrl+Phải)")
        self.stop_button.setAccessibleName("Dừng (Esc)")
        self.mini_button.setAccessibleName("Mini player (Ctrl+M)")
        for button in (self.play_button, self.next_button, self.stop_button, self.mini_button):
            button.setProperty("compact", True)
            button.setMinimumHeight(40)
            controls.addWidget(button)
        row.addLayout(controls)
        self.play_button.clicked.connect(self.play_requested)
        self.next_button.clicked.connect(self.next_requested)
        self.stop_button.clicked.connect(self.stop_requested)
        self.mini_button.clicked.connect(self.mini_requested)
        self.speed.currentIndexChanged.connect(
            lambda _: self.speed_changed.emit(float(self.speed.currentData())))
        self.a_button.clicked.connect(self.set_a_requested)
        self.b_button.clicked.connect(self.set_b_requested)
        self.clear_loop_button.clicked.connect(self.clear_loop_requested)
        self.preview_button.toggled.connect(self.preview_toggled)
        self.keyboard_button.toggled.connect(self.keyboard_toggled)

    def set_compact(self, compact: bool) -> None:
        """Narrow windows hide the runway, so its A–B controls go with it."""
        self.runway.setVisible(not compact)
        for widget in (self.a_button, self.b_button, self.clear_loop_button, self.speed_label):
            widget.setVisible(not compact)

    def set_speed(self, value: float) -> None:
        index = min(range(len(SPEEDS)), key=lambda i: abs(SPEEDS[i] - value))
        blocked = self.speed.blockSignals(True)
        self.speed.setCurrentIndex(index)
        self.speed.blockSignals(blocked)

    def set_status(self, text: str, tone: str = "normal") -> None:
        color = {"normal": "", "danger": Tokens.DANGER, "warning": Tokens.APRICOT,
                 "info": Tokens.SKY_BLUE, "success": Tokens.SUCCESS}[tone]
        self.status.setStyleSheet(f"color: {color};" if color else "")
        self.status.setText(text)

    def sync(self, song: Song | None, state: str) -> None:
        if song:
            self.title.setText(song.title)
            self.title.setToolTip(song.title)
        self.set_status(STATE_LABELS.get(state, state))
        self.play_button.setText(play_label(state))
        self.play_button.setEnabled(state not in {"starting", "stopping"})
        self.next_button.setEnabled(state != "stopping")
        self.stop_button.setEnabled(state not in {"idle", "error"})
        idle = state in {"idle", "error"}
        self.preview_button.setEnabled(idle)
        self.runway.seekable = state in {"idle", "error", "paused"}
        self.runway.set_playing(state == "playing")
