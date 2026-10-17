"""Global hotkeys with a verified listener lifecycle and rollback."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Iterable

from pynput import keyboard
from PySide6.QtCore import QObject, QTimer, Signal

from .domain import Settings
from .i18n import tr

RESERVED = frozenset({"<ctrl>+<alt>+<delete>", "<cmd>+l"})
MODIFIERS = ("ctrl", "alt", "shift", "cmd")
_ALIASES = {
    "escape": "esc", "control": "ctrl", "ctl": "ctrl",
    "return": "enter", "windows": "cmd", "win": "cmd",
    "super": "cmd", "option": "alt", "meta": "cmd",
    "pgup": "page_up", "pgdown": "page_down", "pageup": "page_up", "pagedown": "page_down",
    "del": "delete", "ins": "insert",
}
_SPECIAL = {
    *MODIFIERS, "esc", "enter", "space", "tab", "delete", "backspace", "insert",
    "left", "right", "up", "down", "home", "end", "page_up", "page_down",
    *(f"f{i}" for i in range(1, 25)),
}


def canonical_hotkey(value: str) -> str:
    parts = [_ALIASES.get(part.strip().casefold(), part.strip().casefold())
             for part in value.split("+") if part.strip()]
    ordered = [item for item in MODIFIERS if item in parts]
    ordered.extend(item for item in parts if item not in MODIFIERS)
    return "+".join(f"<{part}>" if part in _SPECIAL else part for part in ordered)


def conflicts_with_music_keys(hotkey: str, music_keys: Iterable[str]) -> bool:
    """A bare music key as a global hotkey would fire on every played note."""
    canonical = canonical_hotkey(hotkey)
    return "+" not in canonical and canonical in {key.casefold() for key in music_keys}


def with_legacy_defaults(settings: Settings) -> Settings:
    hotkeys = dict(settings.hotkeys)
    hotkeys.setdefault("stop", "f10")
    hotkeys.setdefault("next", "f11")
    return replace(settings, hotkeys=hotkeys)


class GlobalHotkeyService(QObject):
    pause_requested, stop_requested, next_requested = Signal(), Signal(), Signal()
    slot_requested = Signal(int)
    error = Signal(str)

    RESERVED = RESERVED

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener = None
        self._settings: Settings | None = None
        self._listener_watch = QTimer(self)
        self._listener_watch.setInterval(500)
        self._listener_watch.timeout.connect(self._check_listener)

    @property
    def active(self) -> bool:
        return self._listener is not None

    def _bindings(self, settings: Settings) -> dict[str, Callable[[], None]]:
        raw: list[tuple[str, Callable[[], None]]] = [
            (settings.pause_hotkey, self.pause_requested.emit),
            (settings.hotkeys.get("stop", "esc"), self.stop_requested.emit),
            (settings.hotkeys.get("next", "f10"), self.next_requested.emit),
        ]
        raw.extend((key, lambda index=index: self.slot_requested.emit(index))  # type: ignore[misc]
                   for index, key in enumerate(settings.hotkey_keys))
        bindings = [(canonical_hotkey(key), callback) for key, callback in raw if key.strip()]
        keys = [key for key, _ in bindings]
        if len(keys) != len(set(keys)):
            raise ValueError(tr("Global hotkeys bị trùng; cấu hình đang dùng được giữ nguyên."))
        if any(key in self.RESERVED for key in keys):
            raise ValueError(
                tr("Một global hotkey được Windows giữ riêng; cấu hình đang dùng được giữ nguyên.")
            )
        for key in keys:
            keyboard.HotKey.parse(key)
        return dict(bindings)

    def start(self, settings: Settings) -> bool:
        try:
            candidate = keyboard.GlobalHotKeys(self._bindings(settings))
        except Exception as exc:
            self.error.emit(tr("Không thể áp dụng global hotkeys: {exc}").format(exc=exc))
            return False

        previous_settings = self._settings
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        try:
            candidate.start()
            wait_until_ready = getattr(candidate, "wait", None)
            if callable(wait_until_ready):
                wait_until_ready()
            join = getattr(candidate, "join", None)
            if callable(join):
                join(0.05)
            is_alive = getattr(candidate, "is_alive", None)
            if callable(is_alive) and not is_alive():
                raise OSError(tr("listener đã dừng trong lúc khởi tạo hook"))
        except Exception as exc:
            try:
                candidate.stop()
            except Exception:
                pass
            if previous_settings is not None:
                try:
                    rollback = keyboard.GlobalHotKeys(self._bindings(previous_settings))
                    rollback.start()
                    self._listener = rollback
                except Exception as rollback_exc:
                    self.error.emit(
                        tr("Không thể bật global hotkeys mới ({exc}); "
                        "khôi phục cấu hình cũ cũng thất bại ({rollback_exc}).").format(
                            exc=exc, rollback_exc=rollback_exc)
                    )
                    return False
            suffix = (
                tr("Cấu hình cũ đã được khôi phục.")
                if previous_settings is not None
                else tr("Chưa có listener nào được bật.")
            )
            self.error.emit(tr("Không thể bật global hotkeys mới: {exc}. {suffix}").format(
                exc=exc, suffix=suffix))
            return False
        self._listener = candidate
        self._settings = settings
        self._listener_watch.start()
        return True

    def _check_listener(self) -> None:
        listener = self._listener
        is_alive = getattr(listener, "is_alive", None) if listener is not None else None
        if callable(is_alive) and not is_alive():
            self._listener = None
            self._listener_watch.stop()
            self.error.emit(
                tr("Global hotkeys đã dừng ngoài dự kiến. Dùng nút Dừng trong ứng dụng "
                "và mở lại ứng dụng để khôi phục hook.")
            )

    def stop(self) -> None:
        self._listener_watch.stop()
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


class DefaultHotkeyService(GlobalHotkeyService):
    """Keeps the legacy F10 stop / F11 next defaults."""

    def start(self, settings: Settings) -> bool:
        return super().start(with_legacy_defaults(settings))


class DisabledHotkeyService(GlobalHotkeyService):
    """Test/headless service that never installs an operating-system hook."""

    def start(self, settings: Settings) -> bool:
        return True

    def stop(self) -> None:
        self._listener = None
