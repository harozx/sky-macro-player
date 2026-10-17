import threading

import pytest

from macro_core import MacroPlayer, SheetValidationError


class FakeClock:
    def __init__(self, hook=None):
        self.now = 0.0
        self.hook = hook

    def __call__(self):
        return self.now

    def sleep(self, duration):
        assert duration >= 0
        self.now += duration
        if self.hook:
            self.hook(self)


class RecordingController:
    def __init__(self, clock, fail_on_press=None):
        self.clock = clock
        self.fail_on_press = fail_on_press
        self.pressed = []
        self.released = []

    def press(self, key):
        if key == self.fail_on_press:
            raise RuntimeError("injected press failure")
        self.pressed.append((key, self.clock()))

    def release(self, key):
        self.released.append((key, self.clock()))


def player(clock=None, controller=None, **kwargs):
    clock = clock or FakeClock()
    controller = controller or RecordingController(clock)
    return MacroPlayer(
        controller=controller,
        clock=clock,
        sleep=clock.sleep,
        poll_interval_sec=.01,
        **kwargs,
    )


def sheet(*notes):
    return {"songNotes": [{"time": stamp, "key": key} for stamp, key in notes]}


def test_absolute_timestamps_do_not_accumulate_key_hold_time():
    clock = FakeClock()
    controller = RecordingController(clock)
    subject = player(clock, controller, key_hold_sec=.05)

    assert subject.play_json_sheet(
        sheet((100, "1Key0"), (200, "1Key1"), (300, "1Key2")),
        threading.Event(),
        countdown_sec=0,
    )

    assert [stamp for _, stamp in controller.pressed] == pytest.approx([.1, .2, .3])
    assert clock.now == pytest.approx(.35)


def test_notes_with_same_timestamp_are_played_as_one_chord():
    clock = FakeClock()
    controller = RecordingController(clock)
    subject = player(clock, controller, key_hold_sec=0)

    subject.play_json_sheet(
        sheet((100, "1Key0"), (100, "1Key1")),
        threading.Event(),
        countdown_sec=0,
    )

    assert controller.pressed == [("y", pytest.approx(.1)), ("u", pytest.approx(.1))]


def test_pause_moves_deadline_by_exact_paused_duration():
    pause = threading.Event()

    def hook(clock):
        if .05 <= clock.now < .06:
            pause.set()
        if clock.now >= .25:
            pause.clear()

    clock = FakeClock(hook)
    controller = RecordingController(clock)
    subject = player(clock, controller, key_hold_sec=0)

    subject.play_json_sheet(
        sheet((100, "1Key0")), threading.Event(), pause, countdown_sec=0
    )

    assert controller.pressed[0][1] == pytest.approx(.30)


def test_stop_during_wait_cancels_without_pressing():
    stop = threading.Event()

    def hook(clock):
        if clock.now >= .04:
            stop.set()

    clock = FakeClock(hook)
    controller = RecordingController(clock)
    subject = player(clock, controller)

    assert not subject.play_json_sheet(
        sheet((100, "1Key0")), stop, countdown_sec=0
    )
    assert controller.pressed == []


def test_input_guard_blocks_note_and_preserves_song_timing():
    state = {"allowed": False}

    def hook(clock):
        if clock.now >= .05:
            state["allowed"] = True

    clock = FakeClock(hook)
    controller = RecordingController(clock)
    subject = player(
        clock, controller, key_hold_sec=0,
        input_guard=lambda: state["allowed"],
    )

    assert subject.play_json_sheet(
        sheet((0, "1Key0"), (100, "1Key1")),
        threading.Event(),
        countdown_sec=0,
    )

    assert [stamp for _, stamp in controller.pressed] == pytest.approx([.05, .15])


def test_focus_loss_inside_chord_releases_without_replaying_sent_key():
    state = {"allowed": True}

    def hook(clock):
        if clock.now >= .05:
            state["allowed"] = True

    clock = FakeClock(hook)

    class FocusChangingController(RecordingController):
        def press(self, key):
            super().press(key)
            if len(self.pressed) == 1:
                state["allowed"] = False

    controller = FocusChangingController(clock)
    subject = player(
        clock, controller, key_hold_sec=0,
        input_guard=lambda: state["allowed"],
    )

    assert subject.play_json_sheet(
        sheet((0, "1Key0"), (0, "1Key1")),
        threading.Event(),
        countdown_sec=0,
    )

    assert controller.pressed == [("y", 0)]
    assert controller.released[0] == ("y", 0)


def test_stop_while_focus_guard_blocks_cancels_without_input():
    stop = threading.Event()

    def hook(clock):
        if clock.now >= .03:
            stop.set()

    clock = FakeClock(hook)
    controller = RecordingController(clock)
    subject = player(
        clock, controller, input_guard=lambda: False,
    )

    assert not subject.play_json_sheet(sheet((0, "1Key0")), stop, countdown_sec=0)
    assert controller.pressed == []


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "songNotes"),
        ({"songNotes": {}}, "songNotes"),
        ({"songNotes": [None]}, "object"),
        ({"songNotes": [{"time": "0", "key": "1Key0"}]}, "time"),
        ({"songNotes": [{"time": -1, "key": "1Key0"}]}, "time"),
        ({"songNotes": [{"time": 0, "key": None}]}, "key"),
    ],
)
def test_malformed_sheet_is_rejected(payload, message):
    with pytest.raises(SheetValidationError, match=message):
        player().play_json_sheet(payload, threading.Event(), countdown_sec=0)


def test_unknown_key_is_not_silently_dropped():
    with pytest.raises(SheetValidationError, match="2Key0"):
        player().play_json_sheet(
            sheet((0, "2Key0")), threading.Event(), countdown_sec=0
        )


def test_input_notes_are_not_mutated():
    payload = sheet((200, "1Key1"), (100, "1Key0"))
    original = [dict(note) for note in payload["songNotes"]]

    player(key_hold_sec=0).play_json_sheet(
        payload, threading.Event(), countdown_sec=0
    )

    assert payload["songNotes"] == original


def test_press_failure_releases_keys_already_pressed():
    clock = FakeClock()
    controller = RecordingController(clock, fail_on_press="u")
    subject = player(clock, controller, key_hold_sec=0)

    with pytest.raises(RuntimeError, match="injected press failure"):
        subject.play_json_sheet(
            sheet((0, "1Key0"), (0, "1Key1")),
            threading.Event(),
            countdown_sec=0,
        )

    assert controller.pressed == [("y", 0)]
    # Release is attempted for the failing key too: press() may fail after the
    # operating system has already accepted the key-down event.
    assert controller.released == [("u", 0), ("y", 0)]


def test_invalid_countdown_is_rejected():
    with pytest.raises(ValueError, match="countdown_sec"):
        player().play_json_sheet(
            sheet((0, "1Key0")), threading.Event(), countdown_sec=-1
        )
