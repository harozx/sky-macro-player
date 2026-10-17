"""Safe, deterministic keyboard playback for Sky music sheets."""
import math
import numbers
import time
from collections.abc import Mapping
from typing import Any, Callable, Iterable, Sequence, SupportsFloat

from pynput import keyboard

from .i18n import N_, tr

MIN_SPEED, MAX_SPEED = .25, 2.


class SheetValidationError(ValueError):
    """Raised when a sheet cannot be played safely and completely."""


class MacroPlayer:
    KEY_LAYOUTS: dict[str, dict[str, Any]] = {
        "old": {"name": N_("Bộ cũ (yuiophjkl;nm,./)"), "json_map": {
            "1Key0": "y", "1Key1": "u", "1Key2": "i", "1Key3": "o", "1Key4": "p",
            "1Key5": "h", "1Key6": "j", "1Key7": "k", "1Key8": "l", "1Key9": ";",
            "1Key10": "n", "1Key11": "m", "1Key12": ",", "1Key13": ".", "1Key14": "/"}},
        "new": {"name": N_("Bộ mới (asdfghjqwertyui)"), "json_map": {
            "1Key0": "a", "1Key1": "s", "1Key2": "d", "1Key3": "f", "1Key4": "g",
            "1Key5": "h", "1Key6": "j", "1Key7": "q", "1Key8": "w", "1Key9": "e",
            "1Key10": "r", "1Key11": "t", "1Key12": "y", "1Key13": "u", "1Key14": "i"}},
    }

    def __init__(self, controller=None, clock=None, sleep=None, *,
                 key_hold_sec=.05, poll_interval_sec=.01,
                 input_guard: Callable[[], bool] | None = None,
                 progress_callback: Callable[[float], None] | None = None,
                 key_callback: Callable[[tuple[str, ...]], None] | None = None,
                 speed: SupportsFloat = 1.):
        self.controller = controller if controller is not None else keyboard.Controller()
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self.key_hold_sec = max(0., float(key_hold_sec))
        self.poll_interval_sec = max(.001, float(poll_interval_sec))
        self.input_guard = input_guard
        self.progress_callback = progress_callback
        self.key_callback = key_callback
        self.speed = speed
        self.current_layout = "old"
        self.json_key_map = self.KEY_LAYOUTS["old"]["json_map"]

    @staticmethod
    def layout_map(keys: Sequence[str]) -> dict[str, str]:
        """Build a ``1Key0..1Key14`` map from 15 distinct single keys."""
        checked = [str(key).strip().casefold() for key in keys]
        if len(checked) != 15 or any(len(key) != 1 or key.isspace() for key in checked):
            raise ValueError(tr("Bộ phím tùy chỉnh cần đúng 15 phím, mỗi ô một ký tự."))
        if len(set(checked)) != 15:
            raise ValueError(tr("Bộ phím tùy chỉnh có phím bị trùng."))
        return {f"1Key{index}": key for index, key in enumerate(checked)}

    def set_custom_layout(self, keys: Sequence[str]) -> None:
        self.json_key_map = self.layout_map(keys)
        self.current_layout = "custom"

    def _current_speed(self) -> float:
        try:
            value = float(self.speed)
        except (TypeError, ValueError):
            return 1.
        if not math.isfinite(value):
            return 1.
        return min(MAX_SPEED, max(MIN_SPEED, value))

    def set_key_layout(self, layout_name):
        if layout_name not in self.KEY_LAYOUTS:
            raise ValueError(tr("Không tìm thấy bộ phím '{layout_name}'.").format(
                layout_name=layout_name))
        self.current_layout = layout_name
        self.json_key_map = self.KEY_LAYOUTS[layout_name]["json_map"]

    def get_layout_name(self):
        if self.current_layout == "custom":
            return tr("Bộ tùy chỉnh")
        return tr(self.KEY_LAYOUTS[self.current_layout]["name"])

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
                raise SheetValidationError(tr("Sheet rỗng; không tìm thấy 'songNotes'."))
            root = root[0]
        if not isinstance(root, Mapping):
            raise SheetValidationError(tr("Sheet phải là object hoặc danh sách chứa object."))
        notes = root.get("songNotes")
        if not isinstance(notes, list):
            raise SheetValidationError(tr("Trường 'songNotes' phải là một danh sách."))
        result = []
        for index, note in enumerate(notes, 1):
            if not isinstance(note, Mapping):
                raise SheetValidationError(tr("Nốt #{index} phải là object.").format(index=index))
            stamp, code = note.get("time"), note.get("key")
            if isinstance(stamp, bool) or not isinstance(stamp, numbers.Real):
                raise SheetValidationError(tr("Nốt #{index} có 'time' không hợp lệ.").format(
                    index=index))
            stamp = float(stamp)
            if not math.isfinite(stamp) or stamp < 0:
                raise SheetValidationError(
                    tr("Nốt #{index} có 'time' âm hoặc không hữu hạn.").format(index=index))
            if not isinstance(code, str) or not code:
                raise SheetValidationError(tr("Nốt #{index} có 'key' không hợp lệ.").format(
                    index=index))
            if code not in self.json_key_map:
                raise SheetValidationError(
                    tr("Nốt #{index} dùng key chưa hỗ trợ '{code}'. "
                    "Sheet 2Key/3Key cần mapping rõ ràng trước khi phát.").format(
                        index=index, code=code))
            result.append((stamp, code))
        return sorted(result, key=lambda item: item[0])

    def _grouped(self, notes: Iterable[tuple[float, str]]):
        grouped: dict[float, list[str]] = {}
        for stamp, code in notes:
            keys = grouped.setdefault(stamp, [])
            key = self.json_key_map[code]
            if key not in keys:
                # Merged layers can name the same key twice in one chord.
                keys.append(key)
        return sorted(grouped.items())

    def play_json_sheet(self, song_data, stop_event, pause_event=None, countdown_sec=3,
                        *, start_ms=0., end_ms=None):
        """Play a sheet; False means cancelled, invalid input/errors are raised."""
        notes = self._validated_notes(song_data)
        return self._play_grouped(self._grouped(notes), stop_event, pause_event,
                                  countdown_sec, start_ms, end_ms)

    def play_events(self, events: Iterable[tuple[float, Sequence[str]]], stop_event,
                    pause_event=None, countdown_sec=0, *, start_ms=0., end_ms=None):
        """Play pre-parsed ``(time_ms, codes)`` events from a validated sheet."""
        notes = []
        for index, (stamp, codes) in enumerate(events, 1):
            for code in codes:
                if code not in self.json_key_map:
                    raise SheetValidationError(
                        tr("Nốt #{index} dùng key chưa hỗ trợ '{code}'. "
                        "Sheet 2Key/3Key cần mapping rõ ràng trước khi phát.").format(
                            index=index, code=code))
                notes.append((float(stamp), code))
        return self._play_grouped(self._grouped(notes), stop_event, pause_event,
                                  countdown_sec, start_ms, end_ms)

    def _play_grouped(self, grouped, stop_event, pause_event, countdown_sec,
                      start_ms, end_ms):
        try:
            countdown = float(countdown_sec)
        except (TypeError, ValueError) as exc:
            raise ValueError(tr("countdown_sec phải là một số không âm.")) from exc
        if not math.isfinite(countdown) or countdown < 0:
            raise ValueError(tr("countdown_sec phải là một số không âm."))
        start_ms = max(0., float(start_ms))
        done, _ = self._wait_until(self._clock() + countdown, stop_event, pause_event)
        if not done:
            return False
        # Song position advances at ``speed`` ms per real ms. Blocked time
        # (pause, focus loss) shifts the clock anchor so no note is skipped.
        state = {"speed": self._current_speed(), "clock": self._clock(),
                 "position": start_ms}

        def position(now):
            return state["position"] + (now - state["clock"]) * 1000. * state["speed"]

        def wait_for(stamp):
            while True:
                if stop_event.is_set():
                    return False
                allowed, blocked = self._wait_while_blocked(stop_event, pause_event)
                if not allowed:
                    return False
                state["clock"] += blocked
                now = self._clock()
                new_speed = self._current_speed()
                if new_speed != state["speed"]:
                    state["position"], state["clock"] = position(now), now
                    state["speed"] = new_speed
                remaining_ms = stamp - position(now)
                if remaining_ms <= 1e-6:
                    return True
                self._sleep(min(self.poll_interval_sec,
                                remaining_ms / 1000. / state["speed"]))

        for stamp, keys in grouped:
            if stamp < start_ms:
                continue
            if end_ms is not None and stamp > end_ms:
                break
            if not wait_for(stamp):
                return False
            if self.progress_callback is not None:
                self.progress_callback(stamp)
            if self.key_callback is not None:
                self.key_callback(tuple(keys))
            played, blocked = self._press_keys_sync("".join(keys), stop_event, pause_event)
            state["clock"] += blocked
            if not played:
                return False
        if end_ms is not None and not wait_for(float(end_ms)):
            return False
        return not stop_event.is_set()
