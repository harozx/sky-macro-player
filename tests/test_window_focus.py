from dataclasses import replace
from pathlib import Path

from macro_player.domain import CURRENT_SETTINGS_VERSION, Settings
from macro_player.repositories import SettingsRepository
from macro_player.window_focus import (
    WindowInfo, choose_sky_window, same_window_identity,
)
from sky_ui_core import Song
from sky_ui_final import MainWindow


class FakeFocusService:
    def __init__(self, *, found=True, activate=True, foreground=True):
        self.window = WindowInfo(
            42, "Sky: Children of the Light", 999, r"C:\\Game\\Sky.exe"
        ) if found else None
        self.activate_result = activate
        self.foreground = foreground
        self.activations = 0

    def find_sky_window(self):
        return self.window

    def activate(self, window):
        self.activations += 1
        return self.activate_result

    def is_foreground(self, window):
        return self.foreground

    def is_window(self, window):
        return window == self.window

    def validate_target(self, window):
        return window == self.window


class FakePlaybackController:
    def __init__(self, *, busy=False, state="idle"):
        self.busy = busy
        self.state = state
        self.layout_name = "old"
        self.played = []
        self.focus_pauses = 0
        self.focus_resumes = 0
        self.input_guard = None

    def play(self, song):
        self.played.append(song)
        return True

    def pause_for_focus(self):
        if self.state not in {"playing", "countdown", "starting"}:
            return False
        self.state = "focus_paused"
        self.focus_pauses += 1
        return True

    def resume_for_focus(self):
        if self.state != "focus_paused":
            return False
        self.state = "playing"
        self.focus_resumes += 1
        return True

    def stop(self):
        self.busy = False
        self.state = "idle"

    def set_input_guard(self, guard):
        self.input_guard = guard


def test_window_chooser_prefers_exact_game_and_excludes_console():
    chosen = choose_sky_window([
        WindowInfo(1, "Sky Instrument Console", 100),
        WindowInfo(2, "A guide to Sky", 200),
        WindowInfo(3, "Sky: Children of the Light", 300, r"C:\\Game\\Sky.exe"),
    ])
    assert chosen is not None
    assert chosen.handle == 3


def test_window_chooser_rejects_exact_title_from_untrusted_process():
    assert choose_sky_window([
        WindowInfo(3, "Sky", 300, r"C:\\Other\\editor.exe"),
    ]) is None


def test_window_chooser_rejects_browser_and_generic_sky_titles():
    assert choose_sky_window([
        WindowInfo(1, "Sky guide - Google Chrome", 100),
        WindowInfo(2, "A guide to Sky", 200),
        WindowInfo(3, "Sky music sheets", 300),
    ]) is None


def test_window_identity_rejects_reused_handle_or_changed_process():
    selected = WindowInfo(42, "Sky: Children of the Light", 900, r"C:\\Game\\Sky.exe")
    assert same_window_identity(
        selected,
        WindowInfo(42, "Sky: Children of the Light", 900, r"C:\\Game\\Sky.exe"),
    )
    assert not same_window_identity(
        selected,
        WindowInfo(42, "Sky: Children of the Light", 901, r"C:\\Game\\Sky.exe"),
    )
    assert not same_window_identity(
        selected,
        WindowInfo(42, "Sky guide - Google Chrome", 900, r"C:\\Game\\Sky.exe"),
    )
    assert not same_window_identity(
        selected,
        WindowInfo(42, "Sky: Children of the Light", 900, r"C:\\Other\\Sky.exe"),
    )
    assert not same_window_identity(
        selected,
        WindowInfo(42, "Sky: Children of the Light", 900),
    )


def test_focus_settings_round_trip(tmp_path: Path):
    repository = SettingsRepository(tmp_path / "settings.json")
    expected = Settings(focus_lock_enabled=True, resume_on_sky_focus=False)
    repository.save(expected)
    actual = repository.load()
    assert actual.focus_lock_enabled is True
    assert actual.resume_on_sky_focus is False
    assert actual.schema_version == CURRENT_SETTINGS_VERSION


def test_locked_play_activates_sky_before_start(qtbot, tmp_path: Path):
    focus = FakeFocusService()
    window = MainWindow(enable_global_hotkeys=False, focus_service=focus)
    qtbot.addWidget(window)
    controller = FakePlaybackController()
    window.controller = controller
    window.settings = replace(window.settings, focus_lock_enabled=True)
    song = Song(tmp_path / "song.txt", "Song")
    window.play_song(song)
    assert focus.activations == 1
    assert controller.played == [song]
    assert controller.input_guard is not None
    assert controller.input_guard() is True


def test_focus_loss_pauses_and_refocus_resumes(qtbot):
    focus = FakeFocusService(foreground=False)
    window = MainWindow(enable_global_hotkeys=False, focus_service=focus)
    qtbot.addWidget(window)
    controller = FakePlaybackController(busy=True, state="playing")
    window.controller = controller
    window.settings = replace(
        window.settings, focus_lock_enabled=True, resume_on_sky_focus=True
    )
    window._poll_focus_lock()
    assert controller.focus_pauses == 1
    assert window.focus_paused is True
    focus.foreground = True
    window._poll_focus_lock()
    assert controller.focus_resumes == 1
    assert window.focus_paused is False


def test_focus_loss_does_not_override_manual_pause(qtbot):
    focus = FakeFocusService(foreground=False)
    window = MainWindow(enable_global_hotkeys=False, focus_service=focus)
    qtbot.addWidget(window)
    controller = FakePlaybackController(busy=True, state="paused")
    window.controller = controller
    window.settings = replace(window.settings, focus_lock_enabled=True)
    window._poll_focus_lock()
    assert controller.focus_pauses == 0
    assert window.focus_paused is False
