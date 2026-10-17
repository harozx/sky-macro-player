"""Safe foreground-window targeting for the optional Sky focus lock."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol


@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    process_id: int = 0
    process_path: str | None = None


_SKY_TITLES = frozenset({"sky", "sky: children of the light"})
_SKY_EXECUTABLES = frozenset({"sky.exe"})


def is_sky_game_title(title: str) -> bool:
    """Return True only for the exact game titles we have observed."""
    normalized = " ".join(title.strip().casefold().split())
    return normalized in _SKY_TITLES


def is_sky_game_process(process_path: str | None) -> bool:
    """Require an observed game executable before accepting an initial target."""
    return bool(process_path and Path(process_path).name.casefold() in _SKY_EXECUTABLES)


def same_window_identity(expected: WindowInfo, current: WindowInfo) -> bool:
    """Protect against a stale/reused HWND by checking its process identity."""
    if expected.handle != current.handle or expected.process_id != current.process_id:
        return False
    if not is_sky_game_title(current.title):
        return False
    if expected.process_path:
        if not current.process_path:
            return False
        return os.path.normcase(expected.process_path) == os.path.normcase(current.process_path)
    return True


def choose_sky_window(windows: Iterable[WindowInfo]) -> WindowInfo | None:
    """Choose an exact Sky game title; never infer from generic/browser titles."""
    candidates: list[WindowInfo] = []
    for window in windows:
        title = window.title.strip()
        lowered = title.casefold()
        if not title or window.process_id == os.getpid():
            continue
        if "macro player" in lowered or "instrument console" in lowered:
            continue
        if not is_sky_game_title(title):
            continue
        if not is_sky_game_process(window.process_path):
            continue
        candidates.append(window)
    # Prefer the full title when both exact variants are visible. Do not guess
    # an executable name: the discovered process identity is retained instead.
    return max(candidates, key=lambda item: len(item.title.strip())) if candidates else None


class FocusService(Protocol):
    def find_sky_window(self) -> WindowInfo | None: ...
    def activate(self, window: WindowInfo) -> bool: ...
    def is_foreground(self, window: WindowInfo) -> bool: ...
    def is_window(self, window: WindowInfo) -> bool: ...
    def validate_target(self, window: WindowInfo) -> bool: ...


class WindowsFocusService:
    """Small User32 adapter kept independent from Qt for deterministic tests."""

    SW_RESTORE = 9
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32 if os.name == "nt" else None
        self._kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None
        if self._user32 is not None:
            wintypes = ctypes.wintypes
            self._user32.GetForegroundWindow.restype = wintypes.HWND
            self._user32.IsWindow.argtypes = [wintypes.HWND]
            self._user32.IsWindow.restype = wintypes.BOOL
            self._user32.IsWindowVisible.argtypes = [wintypes.HWND]
            self._user32.IsWindowVisible.restype = wintypes.BOOL
            self._user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            self._user32.GetWindowTextLengthW.restype = ctypes.c_int
            self._user32.GetWindowTextW.argtypes = [
                wintypes.HWND, wintypes.LPWSTR, ctypes.c_int,
            ]
            self._user32.GetWindowThreadProcessId.argtypes = [
                wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
            ]
            self._user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            self._user32.SetForegroundWindow.restype = wintypes.BOOL
            self._user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            self._kernel32.OpenProcess.argtypes = [
                wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
            ]
            self._kernel32.OpenProcess.restype = wintypes.HANDLE
            self._kernel32.QueryFullProcessImageNameW.argtypes = [
                wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                ctypes.POINTER(wintypes.DWORD),
            ]
            self._kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
            self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    def windows(self) -> tuple[WindowInfo, ...]:
        if self._user32 is None:
            return ()
        results: list[WindowInfo] = []
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
        )

        @callback_type
        def visit(hwnd, _lparam):
            if not self._user32.IsWindowVisible(hwnd):
                return True
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buffer, length + 1)
            process_id = ctypes.c_ulong()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            pid = int(process_id.value)
            results.append(WindowInfo(
                int(hwnd), buffer.value, pid, self._process_path(pid),
            ))
            return True

        self._user32.EnumWindows(visit, 0)
        return tuple(results)

    def find_sky_window(self) -> WindowInfo | None:
        return choose_sky_window(self.windows())

    def _process_path(self, process_id: int) -> str | None:
        if self._kernel32 is None or process_id <= 0:
            return None
        handle = self._kernel32.OpenProcess(
            self.PROCESS_QUERY_LIMITED_INFORMATION, False, process_id,
        )
        if not handle:
            return None
        try:
            size = ctypes.wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not self._kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size),
            ):
                return None
            return str(Path(buffer.value))
        finally:
            self._kernel32.CloseHandle(handle)

    def _window_info(self, handle: int) -> WindowInfo | None:
        if self._user32 is None or not self._user32.IsWindow(handle):
            return None
        length = self._user32.GetWindowTextLengthW(handle)
        if length <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(handle, buffer, length + 1)
        process_id = ctypes.wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(handle, ctypes.byref(process_id))
        pid = int(process_id.value)
        return WindowInfo(handle, buffer.value, pid, self._process_path(pid))

    def validate_target(self, window: WindowInfo) -> bool:
        current = self._window_info(window.handle)
        return current is not None and same_window_identity(window, current)

    def activate(self, window: WindowInfo) -> bool:
        if self._user32 is None or not self.validate_target(window):
            return False
        self._user32.ShowWindow(window.handle, self.SW_RESTORE)
        return bool(self._user32.SetForegroundWindow(window.handle))

    def is_foreground(self, window: WindowInfo) -> bool:
        if self._user32 is None or not self.validate_target(window):
            return False
        return int(self._user32.GetForegroundWindow() or 0) == window.handle

    def is_window(self, window: WindowInfo) -> bool:
        return bool(self._user32 and self._user32.IsWindow(window.handle))
