"""Application icon and system tray menu."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .theme import Tokens


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(Tokens.CLOUD_INK))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * .22, size * .22)
        painter.setBrush(QColor(Tokens.APRICOT))
        painter.drawEllipse(QRectF(size * .18, size * .18, size * .64, size * .64))
        painter.setPen(QColor(Tokens.CLOUD_INK))
        font = QFont(Tokens.BODY)
        font.setPixelSize(max(8, int(size * .46)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, size, size * .98), Qt.AlignmentFlag.AlignCenter, "♪")
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class TrayController(QObject):
    show_requested = Signal()
    play_requested, next_requested, stop_requested = Signal(), Signal(), Signal()
    mini_requested, quit_requested = Signal(), Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.icon = QSystemTrayIcon(app_icon(), self)
        self.icon.setToolTip("Sky Macro Player")
        menu = QMenu()
        self.menu = menu
        self.play_action = QAction("Phát / Tạm dừng", menu)
        actions = (
            ("Mở cửa sổ", self.show_requested),
            (None, None),
            (self.play_action, self.play_requested),
            ("Bài tiếp theo", self.next_requested),
            ("Dừng", self.stop_requested),
            ("Mini player", self.mini_requested),
            (None, None),
            ("Thoát", self.quit_requested),
        )
        for label, signal in actions:
            if label is None:
                menu.addSeparator()
                continue
            action = label if isinstance(label, QAction) else QAction(label, menu)
            action.triggered.connect(signal)
            menu.addAction(action)
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        if self.available():
            self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def set_status(self, song_title: str | None, state_label: str) -> None:
        self.icon.setToolTip(
            f"Sky Macro Player — {state_label}" + (f": {song_title}" if song_title else ""))

    def notify(self, title: str, message: str) -> None:
        if self.icon.isVisible() and self.icon.supportsMessages():
            self.icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_requested.emit()
