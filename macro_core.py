"""Safe, deterministic playback for Sky music sheets."""
import math
import numbers
import threading
import time
from collections.abc import Mapping
from typing import Callable
from pynput import keyboard


class SheetValidationError(ValueError):
    """Raised when a sheet cannot be played safely and completely."""


class MacroPlayer:
    KEY_LAYOUTS = {
        "old": {"name": "Bộ cũ (yuiophjkl;nm,./)", "json_map": {
            "1Key0": "y", "1Key1": "u", "1Key2": "i", "1Key3": "o", "1Key4": "p",
            "1Key5": "h", "1Key6": "j", "1Key7": "k", "1Key8": "l", "1Key9": ";",
            "1Key10": "n", "1Key11": "m", "1Key12": ",", "1Key13": ".", "1Key14": "/"}},
        "new": {"name": "Bộ mới (asdfghjqwertyui)", "json_map": {
            "1Key0": "a", "1Key1": "s", "1Key2": "d", "1Key3": "f", "1Key4": "g",
            "1Key5": "h", "1Key6": "j", "1Key7": "q", "1Key8": "w", "1Key9": "e",
            "1Key10": "r", "1Key11": "t", "1Key12": "y", "1Key13": "u", "1Key14": "i"}},
    }

    def __init__(self, controller=None, clock=None, sleep=None, *,
                 key_hold_sec=.05, poll_interval_sec=.01,
                 input_guard: Callable[[], bool] | None = None,
                 progress_callback: Callable[[float], None] | None = None):
        self.controller = controller if controller is not None else keyboard.Controller()
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self.key_hold_sec = max(0., float(key_hold_sec))
        self.poll_interval_sec = max(.001, float(poll_interval_sec))
        self.input_guard = input_guard
        self.progress_callback = progress_callback
        self.current_layout = "old"
        self.json_key_map = self.KEY_LAYOUTS["old"]["json_map"]

    def set_key_layout(self, layout_name):
        if layout_name not in self.KEY_LAYOUTS:
            raise ValueError(f"Không tìm thấy bộ phím '{layout_name}'.")
        self.current_layout = layout_name
        self.json_key_map = self.KEY_LAYOUTS[layout_name]["json_map"]

    def get_layout_name(self):
        return self.KEY_LAYOUTS[self.current_layout]["name"]

    def _string_to_key(self, key_str):
        return key_str

    def _input_allowed(self):
        if self.input_guard is None:
            return True
        try:
            return bool(self.input_guard())
        except Exception:
            # A failed safety check must never authorize keyboard input.
            return False

    def _wait_while_blocked(self, stop_event, pause_event=None):
        """Wait until manual pause/focus guard clears; return blocked time."""
        blocked_at = None
        while ((pause_event is not None and pause_event.is_set())
               or not self._input_allowed()):
            if stop_event is not None and stop_event.is_set():
                blocked = 0. if blocked_at is None else self._clock() - blocked_at
                return False, blocked
            if blocked_at is None:
                blocked_at = self._clock()
            self._sleep(self.poll_interval_sec)
        blocked = 0. if blocked_at is None else self._clock() - blocked_at
        return True, blocked

    def _press_keys_sync(self, keys_str, stop_event=None, pause_event=None):
        """Press each chord key at most once and always release held keys."""
        if keys_str == "SILENT":
            return True, 0.
        if stop_event is not None and stop_event.is_set():
            return False, 0.
        blocked_total = 0.
        allowed, blocked = self._wait_while_blocked(stop_event, pause_event)
        blocked_total += blocked
        if not allowed:
            return False, blocked_total
        pressed, primary_error, interrupted = [], None, False
        try:
            for key in map(self._string_to_key, keys_str):
                if stop_event is not None and stop_event.is_set():
                    return False, blocked_total
                if ((pause_event is not None and pause_event.is_set())
                        or not self._input_allowed()):
                    interrupted = True
                    break
                # Record before press: some backends can accept key-down and
                # then raise, so release must still be attempted.
                pressed.append(key)
                self.controller.press(key)
            deadline = self._clock() + self.key_hold_sec
            while not interrupted and self._clock() < deadline:
                if ((pause_event is not None and pause_event.is_set())
                        or not self._input_allowed()):
                    interrupted = True
                    break
                if stop_event is not None and stop_event.is_set():
                    return False, blocked_total
                self._sleep(min(self.poll_interval_sec, deadline - self._clock()))
            if not interrupted:
                return True, blocked_total
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            release_error = None
            for key in reversed(pressed):
                try:
                    self.controller.release(key)
                except BaseException as exc:
                    release_error = release_error or exc
            if primary_error is None and release_error is not None:
                raise release_error
        # The partial chord is consumed. Waiting here keeps later notes aligned
        # without replaying a key-down that another application may have seen.
        allowed, blocked = self._wait_while_blocked(stop_event, pause_event)
        return allowed, blocked_total + blocked

    def _wait_until(self, target, stop_event, pause_event):
        """Wait for an absolute deadline; return its pause-adjusted value."""
        while True:
            if stop_event.is_set():
                return False, target
            allowed, blocked = self._wait_while_blocked(stop_event, pause_event)
            if not allowed:
                return False, target
            target += blocked
            remaining = target - self._clock()
            if remaining <= 0:
                return True, target
            self._sleep(min(self.poll_interval_sec, remaining))

    def _interruptible_sleep(self, duration_sec, stop_event, pause_event):
        done, _ = self._wait_until(
            self._clock() + max(0., duration_sec), stop_event, pause_event)
        return done

    def _validated_notes(self, song_data):
        root = song_data
        if isinstance(root, list):
            if not root:
                raise SheetValidationError("Sheet rỗng; không tìm thấy 'songNotes'.")
            root = root[0]
        if not isinstance(root, Mapping):
            raise SheetValidationError("Sheet phải là object hoặc danh sách chứa object.")
        notes = root.get("songNotes")
        if not isinstance(notes, list):
            raise SheetValidationError("Trường 'songNotes' phải là một danh sách.")
        result = []
        for index, note in enumerate(notes, 1):
            if not isinstance(note, Mapping):
                raise SheetValidationError(f"Nốt #{index} phải là object.")
            stamp, code = note.get("time"), note.get("key")
            if isinstance(stamp, bool) or not isinstance(stamp, numbers.Real):
                raise SheetValidationError(f"Nốt #{index} có 'time' không hợp lệ.")
            stamp = float(stamp)
            if not math.isfinite(stamp) or stamp < 0:
                raise SheetValidationError(f"Nốt #{index} có 'time' âm hoặc không hữu hạn.")
            if not isinstance(code, str) or not code:
                raise SheetValidationError(f"Nốt #{index} có 'key' không hợp lệ.")
            if code not in self.json_key_map:
                raise SheetValidationError(
                    f"Nốt #{index} dùng key chưa hỗ trợ '{code}'. "
                    "Sheet 2Key/3Key cần mapping rõ ràng trước khi phát.")
            result.append((stamp, code))
        return sorted(result, key=lambda item: item[0])

    def play_json_sheet(self, song_data, stop_event, pause_event=None, countdown_sec=3):
        """Play a sheet; False means cancelled, invalid input/errors are raised."""
        notes = self._validated_notes(song_data)
        try:
            countdown = float(countdown_sec)
        except (TypeError, ValueError) as exc:
            raise ValueError("countdown_sec phải là một số không âm.") from exc
        if not math.isfinite(countdown) or countdown < 0:
            raise ValueError("countdown_sec phải là một số không âm.")
        done, _ = self._wait_until(self._clock() + countdown, stop_event, pause_event)
        if not done:
            return False
        started, pause_offset, grouped = self._clock(), 0., {}
        for stamp, code in notes:
            grouped.setdefault(stamp, []).append(self.json_key_map[code])
        for stamp, keys in grouped.items():
            target = started + pause_offset + stamp / 1000.
            done, adjusted = self._wait_until(target, stop_event, pause_event)
            pause_offset += adjusted - target
            if not done:
                return False
            if self.progress_callback is not None:
                self.progress_callback(stamp)
            played, blocked = self._press_keys_sync(
                "".join(keys), stop_event, pause_event,
            )
            pause_offset += blocked
            if not played:
                return False
        return not stop_event.is_set()
