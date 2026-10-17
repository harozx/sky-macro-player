"""Reusable widgets: Note Runway, key grid, hotkey capture field."""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QSizePolicy, QWidget

from .theme import Tokens


def format_duration(milliseconds: int) -> str:
    seconds = max(0, int(milliseconds) // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


class NoteRunway(QWidget):
    """Signature timeline: notes travel along a staff toward a warm playhead.

    Progress is interpolated from a monotonic clock and reconciled with the
    engine's authoritative position on every played note. When idle or paused
    the runway is clickable to choose a start position.
    """

    position_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(74)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Tiến trình nốt nhạc")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._moments: list[int] = []
        self._duration, self._elapsed = 1, 0
        self._elapsed_before_run = 0
        self._playing = self._reduced_motion = False
        self.speed = 1.0
        self.seekable = False
        self.cursor_ms: int | None = None
        self.loop_a: int | None = None
        self.loop_b: int | None = None
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    @property
    def duration(self) -> int:
        return self._duration

    @property
    def elapsed(self) -> int:
        self._sync_elapsed()
        return int(self._elapsed)

    def set_timeline(self, moments: list[int], duration: int) -> None:
        self._moments, self._duration, self._elapsed = list(moments), max(1, duration), 0
        self._elapsed_before_run = 0
        self._clock.invalidate()
        self.update()

    def set_progress(self, elapsed: int) -> None:
        """Reconcile visual interpolation with an authoritative engine position."""
        self._elapsed = max(0, min(self._duration, int(elapsed)))
        self._elapsed_before_run = self._elapsed
        if self._playing:
            self._clock.restart()
        self.update()

    def set_speed(self, value: float) -> None:
        self._sync_elapsed()
        self._elapsed_before_run = self._elapsed
        if self._playing:
            self._clock.restart()
        self.speed = float(value)

    def set_playing(self, value: bool) -> None:
        if value == self._playing:
            return
        if self._playing:
            self._sync_elapsed()
            self._elapsed_before_run = self._elapsed
        self._playing = value
        if value:
            self._clock.restart()
            self._timer.setInterval(33)
            if not self._reduced_motion:
                self._timer.start()
        else:
            self._clock.invalidate()
            self._timer.stop()
        self.update()

    def set_reduced_motion(self, value: bool) -> None:
        self._reduced_motion = value
        if value:
            self._timer.stop()
        elif self._playing:
            self._timer.start()

    def reset(self) -> None:
        self._timer.stop()
        self._clock.invalidate()
        self._elapsed = self._elapsed_before_run = 0
        self._playing = False
        self.update()

    def _tick(self) -> None:
        self._sync_elapsed()
        self.update()

    def _sync_elapsed(self) -> None:
        """Derive progress from a monotonic clock so delayed paint ticks do not drift."""
        if self._playing and self._clock.isValid():
            self._elapsed = min(
                self._duration,
                self._elapsed_before_run + self._clock.elapsed() * self.speed,
            )

    def sizeHint(self) -> QSize:
        return QSize(500, 74)

    def _geometry(self) -> tuple[QRectF, float, float]:
        bounds = QRectF(self.rect().adjusted(8, 8, -8, -8))
        playhead = bounds.left() + bounds.width() * .26
        return bounds, playhead, bounds.width() * .72

    def position_at(self, x: float) -> int:
        _, playhead, span = self._geometry()
        position = self._elapsed + (x - playhead) / max(1., span) * self._duration
        return int(max(0, min(self._duration, position)))

    def _x_for(self, moment: float) -> float:
        _, playhead, span = self._geometry()
        return playhead + (moment - self._elapsed) / self._duration * span

    def mousePressEvent(self, event) -> None:
        if self.seekable and self._moments and event.button() == Qt.MouseButton.LeftButton:
            self.position_clicked.emit(self.position_at(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        self._sync_elapsed()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds, playhead, _ = self._geometry()
        gradient = QLinearGradient(bounds.topLeft(), bounds.topRight())
        gradient.setColorAt(0, QColor(Tokens.DEEP_SLATE))
        gradient.setColorAt(1, QColor("#1D3045"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(bounds, 10, 10)
        center = bounds.center().y()
        if self.loop_a is not None and self.loop_b is not None:
            left, right = self._x_for(self.loop_a), self._x_for(self.loop_b)
            band = QColor(Tokens.APRICOT)
            band.setAlphaF(.12)
            painter.setBrush(band)
            painter.drawRect(QRectF(max(bounds.left(), left), bounds.top() + 4,
                                    max(0., min(bounds.right(), right) - max(bounds.left(), left)),
                                    bounds.height() - 8))
        painter.setPen(QPen(QColor(Tokens.BORDER), 1))
        for offset in (-16, -8, 0, 8, 16):
            painter.drawLine(int(bounds.left() + 12), int(center + offset),
                             int(bounds.right() - 12), int(center + offset))
        for marker, label in ((self.loop_a, "A"), (self.loop_b, "B"), (self.cursor_ms, "")):
            if marker is None:
                continue
            x = self._x_for(marker)
            if bounds.left() <= x <= bounds.right():
                painter.setPen(QPen(QColor(Tokens.SKY_BLUE), 1, Qt.PenStyle.DashLine))
                painter.drawLine(int(x), int(bounds.top() + 6), int(x), int(bounds.bottom() - 6))
                if label:
                    painter.drawText(QPointF(x + 3, bounds.top() + 15), label)
        painter.setPen(QPen(QColor(Tokens.APRICOT), 2))
        painter.drawLine(int(playhead), int(bounds.top() + 7), int(playhead), int(bounds.bottom() - 7))
        painter.setPen(Qt.PenStyle.NoPen)
        for index, moment in enumerate(self._moments):
            x = self._x_for(moment)
            if bounds.left() + 8 <= x <= bounds.right() - 8:
                color = QColor(Tokens.SKY_BLUE)
                color.setAlphaF(max(.2, 1 - abs(x - playhead) / max(1., bounds.width()) * 1.8))
                painter.setBrush(color)
                painter.drawEllipse(QPointF(x, center + ((index % 5) - 2) * 8), 3.2, 3.2)
        painter.setPen(QColor(Tokens.HUSHED_BLUE))
        painter.setFont(QFont(Tokens.UTILITY, 8))
        painter.drawText(
            bounds.adjusted(0, 0, -10, -4),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            f"{format_duration(self._elapsed)} / {format_duration(self._duration)}",
        )


class KeyGrid(QWidget):
    """The 15 in-game keys as a 3×5 grid that lights up as notes are played."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Bàn phím 15 nốt")
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        self.cells: list[QLabel] = []
        for index in range(15):
            cell = QLabel("")
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setFixedSize(34, 24)
            cell.setFont(QFont(Tokens.UTILITY, 10))
            grid.addWidget(cell, index // 5, index % 5)
            self.cells.append(cell)
        self._labels: list[str] = [""] * 15
        self._lit: set[int] = set()
        self._decay = QTimer(self)
        self._decay.setSingleShot(True)
        self._decay.setInterval(160)
        self._decay.timeout.connect(self.clear)
        self._paint_cells()

    def set_labels(self, keys: list[str]) -> None:
        self._labels = [str(key) for key in keys][:15] + [""] * max(0, 15 - len(keys))
        for cell, label in zip(self.cells, self._labels):
            cell.setText(label.upper() if label != ";" else ";")
        self.clear()

    def flash(self, keys: list[str]) -> None:
        wanted = {str(key) for key in keys}
        self._lit = {index for index, label in enumerate(self._labels) if label in wanted}
        self._paint_cells()
        self._decay.start()

    def lit_labels(self) -> list[str]:
        return [self._labels[index] for index in sorted(self._lit)]

    def clear(self) -> None:
        self._lit = set()
        self._paint_cells()

    def _paint_cells(self) -> None:
        for index, cell in enumerate(self.cells):
            lit = index in self._lit
            cell.setStyleSheet(
                f"border-radius: 8px; border: 1px solid "
                f"{Tokens.APRICOT if lit else Tokens.BORDER};"
                f"background: {Tokens.APRICOT if lit else Tokens.CLOUD_INK};"
                f"color: {Tokens.CLOUD_INK if lit else Tokens.MOON_MIST};"
                f"font-weight: {'700' if lit else '400'};"
            )


_QT_KEY_NAMES = {
    Qt.Key.Key_Escape: "Esc", Qt.Key.Key_Space: "Space", Qt.Key.Key_Return: "Enter",
    Qt.Key.Key_Enter: "Enter", Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down", Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End", Qt.Key.Key_PageUp: "Page_Up", Qt.Key.Key_PageDown: "Page_Down",
    Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Delete: "Delete",
}
_MODIFIER_KEYS = {
    Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock,
}


def hotkey_from_event(key: int, modifiers: Qt.KeyboardModifier, text: str = "") -> str | None:
    """Convert a key press to the ``Ctrl+Shift+F8`` notation; None for bare modifiers."""
    key = Qt.Key(key)
    if key in _MODIFIER_KEYS:
        return None
    shifted_symbol = False
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        name = f"F{int(key) - int(Qt.Key.Key_F1) + 1}"
    elif key in _QT_KEY_NAMES:
        name = _QT_KEY_NAMES[key]
    elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        name = chr(int(key))
    elif text and text.isprintable() and not text.isspace():
        name = text
        shifted_symbol = True
    else:
        return None
    parts = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier and not shifted_symbol:
        parts.append("Shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("Win")
    return "+".join([*parts, name])


class HotkeyEdit(QLineEdit):
    """Press a key combination to record it; Backspace clears; Tab moves focus."""

    def __init__(self, value: str = "", parent: QWidget | None = None) -> None:
        super().__init__(value, parent)
        self.setPlaceholderText("Nhấn tổ hợp phím…")
        self.setToolTip("Nhấn tổ hợp phím muốn dùng. Backspace để xóa, Tab để chuyển ô.")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()
        bare = not (modifiers & (Qt.KeyboardModifier.ControlModifier
                                 | Qt.KeyboardModifier.AltModifier
                                 | Qt.KeyboardModifier.MetaModifier))
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and bare:
            super().keyPressEvent(event)
            return
        if key == Qt.Key.Key_Backspace and bare:
            self.clear()
            event.accept()
            return
        value = hotkey_from_event(key, modifiers, event.text())
        if value is not None:
            self.setText(value)
            self.editingFinished.emit()
        event.accept()
