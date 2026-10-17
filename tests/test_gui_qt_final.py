from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QKeySequence

from macro_player.domain import Settings
from macro_player.repositories import SettingsRepository
from sky_ui_core import Song
from sky_ui_final import DefaultHotkeyService, EditableHotkeysPage, MainWindow


class FakeHotkeys(QObject):
    pause_requested, stop_requested, next_requested = Signal(), Signal(), Signal()
    slot_requested = Signal(int)
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.started = []
        self.stop_count = 0

    def start(self, settings):
        self.started.append(settings)
        return True

    def stop(self):
        self.stop_count += 1


class FakeController:
    def __init__(self, *, busy=False):
        self.busy = busy
        self.state = "playing" if busy else "idle"
        self.stop_count = 0
        self.played = []

    def stop(self):
        self.stop_count += 1
        self.state = "stopping"

    def play(self, song):
        self.played.append(song)
        return True


class FakeCloseEvent:
    def __init__(self):
        self.accepted = False
        self.ignored = False

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def test_window_can_disable_system_hotkeys(qtbot):
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    assert window.hotkeys._listener is None


def test_hotkey_editor_rejects_duplicates(qtbot):
    page = EditableHotkeysPage(Settings(), [])
    qtbot.addWidget(page)
    page.action_fields["pause"].setText("F10")
    page.action_fields["stop"].setText("f10")
    valid, message = page.validate_values()
    assert not valid
    assert "nhiều hành động" in message


def test_hotkey_editor_persists_and_restarts_service(qtbot, tmp_path: Path):
    fake = FakeHotkeys()
    window = MainWindow(hotkey_service=fake)
    qtbot.addWidget(window)
    window.settings_repository = SettingsRepository(tmp_path / "settings.json")
    window.hotkeys_page.action_fields["pause"].setText("F8")
    window.hotkeys_page.action_fields["stop"].setText("F10")
    window.hotkeys_page.action_fields["next"].setText("F11")
    window.hotkeys_page._save()
    saved = window.settings_repository.load()
    assert saved.pause_hotkey == "F8"
    assert saved.hotkeys["stop"] == "F10"
    assert saved.hotkeys["next"] == "F11"
    assert fake.started[-1] == saved


def test_hotkey_save_backs_up_invalid_settings(qtbot, tmp_path: Path):
    fake = FakeHotkeys()
    window = MainWindow(hotkey_service=fake)
    qtbot.addWidget(window)
    path = tmp_path / "settings.json"
    original = b'{"countdown_seconds": "broken"}'
    path.write_bytes(original)
    window.settings_repository = SettingsRepository(path)
    window.settings_error = "broken settings"
    window.hotkeys_page._save()
    backups = list(tmp_path.glob("settings.json.invalid*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert window.settings_error is None


def test_legacy_hotkey_defaults_are_f10_stop_f11_next(monkeypatch):
    captured = {}

    def fake_start(self, settings):
        captured.update(settings.hotkeys)
        return True

    monkeypatch.setattr("sky_ui_integrated.GlobalHotkeyService.start", fake_start)
    assert DefaultHotkeyService().start(Settings())
    assert captured["stop"] == "f10"
    assert captured["next"] == "f11"


def test_escape_routes_to_replacement_controller(qtbot):
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    replacement = FakeController()
    window.controller = replacement

    escape = next(
        action for action in window.actions()
        if action.shortcut() == QKeySequence("Escape")
    )
    escape.trigger()

    assert replacement.stop_count == 1


def test_space_does_not_start_playback_while_typing_in_search(qtbot):
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    played = []
    window.controller.play = played.append
    window.library_page.search.setFocus()
    qtbot.keyClick(window.library_page.search, Qt.Key.Key_Space)
    assert played == []


def test_queue_can_be_reopened_in_narrow_window(qtbot):
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    window.resize(820, 600)
    window.show()
    qtbot.wait(20)
    assert not window.queue.isVisible()
    window.queue_toggle.click()
    assert window.queue.isVisible()


def test_close_stops_hotkeys_and_prevents_pending_restart(qtbot, tmp_path: Path):
    hotkeys = FakeHotkeys()
    window = MainWindow(hotkey_service=hotkeys)
    qtbot.addWidget(window)
    controller = FakeController(busy=True)
    window.controller = controller
    pending = Song(tmp_path / "pending.txt", "Pending")
    queued = Song(tmp_path / "queued.txt", "Queued")
    window.pending_song = pending
    window.queue.add_song(queued)
    queued_count = window.queue.list.count()
    event = FakeCloseEvent()

    window.closeEvent(event)

    assert event.ignored is True
    assert window._closing is True
    assert window.pending_song is None
    assert controller.stop_count == 1
    assert hotkeys.stop_count == 1
    assert not window.focus_timer.isActive()

    window.play_song(pending)
    assert controller.played == []

    controller.busy = False
    window._playback_finished(completed=True)
    assert window.queue.list.count() == queued_count


def test_stop_invalidates_already_scheduled_song(qtbot, tmp_path: Path) -> None:
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    controller = FakeController()
    window.controller = controller
    song = Song(tmp_path / "late.txt", "Late")
    generation = window._command_generation
    window.stop_playback()
    window._play_if_current(song, generation)
    assert controller.played == []


def test_queue_item_is_kept_when_play_is_rejected(qtbot, tmp_path: Path) -> None:
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    song = Song(tmp_path / "queued.txt", "Queued")
    window.queue.add_song(song)
    window.play_song = lambda _song: False
    window.play_next()
    assert window.queue.peek_next() == song


def test_scheduled_queue_item_survives_stop_before_callback(qtbot, tmp_path: Path) -> None:
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    controller = FakeController()
    window.controller = controller
    song = Song(tmp_path / "queued.txt", "Queued")
    window.queue.add_song(song)
    generation = window._command_generation
    window.stop_playback()
    window._play_queue_if_current(song, generation)
    assert window.queue.peek_next() == song
    assert controller.played == []
