import json
from dataclasses import replace
from pathlib import Path

import pytest

import macro_player.hotkeys as hotkeys_module
from macro_player.domain import Settings
from macro_player.hotkeys import GlobalHotkeyService, canonical_hotkey
from macro_player.library import Song
from macro_player.repositories import (
    FavoritesRepository,
    RepositoryError,
    SettingsRepository,
    SheetRepository,
)
from macro_player.ui.hotkeys_page import EditableHotkeysPage
from macro_player.ui.main_window import MainWindow


def test_sheet_audit_reports_unsupported_keys_before_play(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    (sheets / "unsupported.json").write_text(
        json.dumps({
            "songNotes": [
                {"time": 0, "key": "1Key0"},
                {"time": 10, "key": ["1Key1", "2Key0"]},
            ]
        }),
        encoding="utf-8",
    )
    audit = SheetRepository(sheets).audit(
        "unsupported.json", {"1Key0", "1Key1"}
    )
    assert not audit.playable
    assert audit.note_count == 2
    assert audit.unsupported_keys == ("2Key0",)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Shift+Ctrl+A", "<ctrl>+<shift>+a"),
        ("CTRL + shift + a", "<ctrl>+<shift>+a"),
        ("Windows+L", "<cmd>+l"),
    ],
)
def test_canonical_hotkey_normalizes_aliases_and_modifier_order(raw, expected) -> None:
    assert canonical_hotkey(raw) == expected


def test_hotkey_failure_restores_previous_listener(monkeypatch, qtbot) -> None:
    listeners = []

    class FakeListener:
        def __init__(self, bindings):
            self.bindings = bindings
            self.stopped = False
            listeners.append(self)

        def start(self):
            if "<f8>" in self.bindings:
                raise OSError("hook failed")

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(hotkeys_module.keyboard, "GlobalHotKeys", FakeListener)
    service = GlobalHotkeyService()
    assert service.start(Settings())
    assert not service.start(Settings(pause_hotkey="f8"))
    assert service._listener is listeners[-1]
    assert "<f9>" in service._listener.bindings


def test_hotkey_listener_that_dies_during_start_is_rejected(monkeypatch) -> None:
    class DeadListener:
        def __init__(self, bindings):
            self.bindings = bindings
        def start(self):
            pass
        def wait(self):
            pass
        def join(self, timeout):
            pass
        def is_alive(self):
            return False
        def stop(self):
            pass
    monkeypatch.setattr(hotkeys_module.keyboard, "GlobalHotKeys", DeadListener)
    service = GlobalHotkeyService()
    assert not service.start(Settings())
    assert service._listener is None


def test_hotkey_listener_death_after_start_is_reported(monkeypatch, qtbot) -> None:
    class Listener:
        alive = True
        def __init__(self, bindings):
            self.bindings = bindings
        def start(self):
            pass
        def is_alive(self):
            return self.alive
        def stop(self):
            self.alive = False
    monkeypatch.setattr(hotkeys_module.keyboard, "GlobalHotKeys", Listener)
    service = GlobalHotkeyService()
    errors = []
    service.error.connect(errors.append)
    assert service.start(Settings())
    service._listener.alive = False
    service._check_listener()
    assert service._listener is None
    assert errors and "ngoài dự kiến" in errors[-1]


def test_restore_settings_does_not_write_through_widget_signals(qtbot) -> None:
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)

    class NoWriteRepository:
        def save(self, settings):
            raise AssertionError("restore must not save settings")

    window.settings_repository = NoWriteRepository()
    window.settings = replace(
        window.settings,
        countdown_seconds=30,
        always_on_top=False,
        reduced_motion=True,
    )
    window._apply_settings()
    assert window.settings_page.countdown.value() == 30
    assert window.settings_page.countdown_value.text() == "30 giây"
    assert window.settings_page.reduced_motion.isChecked()


def test_recover_invalid_settings_preserves_original_bytes(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    original = b'{"countdown_seconds": "broken"}'
    path.write_bytes(original)
    repository = SettingsRepository(path)
    backup = repository.recover(Settings(countdown_seconds=7))
    assert backup is not None and backup.read_bytes() == original
    assert repository.load().countdown_seconds == 7


def test_recover_invalid_favorites_preserves_original_bytes(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    (sheets / "song.txt").write_text('{"songNotes": []}', encoding="utf-8")
    path = tmp_path / "favorites.json"
    original = b'{"favorites": "broken"}'
    path.write_bytes(original)
    repository = FavoritesRepository(path, sheets)
    backup = repository.recover(["song.txt"])
    assert backup is not None and backup.read_bytes() == original
    assert repository.load()[0].path == "song.txt"


def test_enabling_focus_lock_while_busy_is_rejected(qtbot) -> None:
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    original = window.settings.focus_lock_enabled
    window.controller._thread = type("Busy", (), {"isRunning": lambda self: True})()
    window.settings_page.focus_lock_checkbox.setChecked(not original)
    assert window.settings.focus_lock_enabled is original
    assert "dừng bài" in window.dock.status.text().casefold()
    window.controller._thread = None


def test_favorite_save_error_keeps_existing_ui_state(qtbot) -> None:
    window = MainWindow(enable_global_hotkeys=False)
    qtbot.addWidget(window)
    song = window.songs[0]
    before = [(item.path, item.favorite) for item in window.songs]

    def broken_save(paths):
        raise RepositoryError("read only")

    window.library.save_favorites = broken_save
    window.toggle_favorite(song)
    assert [(item.path, item.favorite) for item in window.songs] == before


def test_song_slot_uses_full_relative_identity(qtbot) -> None:
    songs = [
        Song(Path("a") / "song.txt", "A", relative="a/song.txt"),
        Song(Path("b") / "song.txt", "B", relative="b/song.txt"),
    ]
    settings = Settings(song_slots=("b/song.txt",) + (None,) * 7)
    page = EditableHotkeysPage(settings, songs)
    qtbot.addWidget(page)
    assert page.slot_fields[0][1].currentData() == "b/song.txt"
    values = [page.slot_fields[0][1].itemData(index)
              for index in range(1, page.slot_fields[0][1].count())]
    assert values == ["a/song.txt", "b/song.txt"]
