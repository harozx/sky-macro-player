import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

import macro_player.playback as playback_module
from macro_player.hotkeys import canonical_hotkey
from macro_player.library import Library, Song
from macro_player.paths import bundled_sheets_dir
from macro_player.playback import PlaybackController, load_song_events
from macro_player.ui.library_page import LibraryPage
from macro_player.ui.mini import MiniOverlay
from macro_player.ui.widgets import NoteRunway


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def test_loader_reads_utf16_real_sheet():
    candidates = list(bundled_sheets_dir().glob("*.txt"))
    boms = (bytes([0xFF, 0xFE]), bytes([0xFE, 0xFF]))
    utf16 = next(path for path in candidates if path.read_bytes().startswith(boms))
    events, moments, duration = load_song_events(Song(utf16, "x"))
    assert events
    assert moments == sorted(moments)
    assert duration == moments[-1]


def test_library_discovers_real_dataset(tmp_path: Path):
    songs = Library(bundled_sheets_dir(), tmp_path / "fav.json").scan(
        [f"1Key{i}" for i in range(15)])
    assert len(songs) >= 100
    assert all(song.path.is_file() for song in songs)


def test_library_accepts_legacy_favorite_records(tmp_path: Path):
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    (sheets / "Song.txt").write_text(json.dumps({"songNotes": []}))
    target = tmp_path / "favorites.json"
    target.write_text(json.dumps([
        {"name": "Song.txt", "type": "JSON", "path": "sheets\\Song.txt"},
    ]))
    assert Library(sheets, target).load_favorites() == {"song.txt"}


def test_library_filter_hides_non_matching_song(app):
    page = LibraryPage([
        Song(Path("alpha.txt"), "Alpha"), Song(Path("beta.txt"), "Beta", True),
    ])
    page.search.setText("beta")
    assert page.list.item(0).isHidden()
    assert not page.list.item(1).isHidden()


def test_note_runway_reduced_motion_stops_timer(app):
    runway = NoteRunway()
    runway.set_timeline([0, 100, 200], 200)
    runway.set_playing(True)
    assert runway._timer.isActive()
    runway.set_reduced_motion(True)
    assert not runway._timer.isActive()


def test_note_runway_uses_elapsed_clock_instead_of_timer_ticks(app):
    class FakeElapsedClock:
        def __init__(self):
            self.valid = False
            self.value = 0

        def restart(self):
            self.valid = True
            self.value = 0

        def invalidate(self):
            self.valid = False

        def isValid(self):
            return self.valid

        def elapsed(self):
            return self.value

    runway = NoteRunway()
    runway._clock = clock = FakeElapsedClock()
    runway.set_timeline([0, 500, 1000], 1000)
    runway.set_playing(True)
    clock.value = 420
    runway._tick()
    assert runway._elapsed == 420
    runway.set_playing(False)
    clock.value = 900
    runway._tick()
    assert runway._elapsed == 420


def test_note_runway_reconciles_authoritative_progress(app):
    runway = NoteRunway()
    runway.set_timeline([0, 500, 1000], 1000)
    runway.set_playing(True)
    runway.set_progress(640)
    assert runway._elapsed == 640
    assert runway._elapsed_before_run == 640


def test_mini_overlay_reports_focus_pause_and_keeps_stop_visible(app):
    mini = MiniOverlay()
    mini.sync(Song(Path("song.txt"), "Một tên bài rất dài"), "focus_paused")
    assert mini.status.text() == "Đang chờ cửa sổ Sky"
    assert mini.play_button.text() == "Tiếp tục"
    assert mini.stop_button.minimumHeight() >= 44
    mini.set_progress(65000, 125000)
    assert mini.time_label.text() == "1:05 / 2:05"


def test_controller_keeps_error_state_after_worker_finishes(qtbot, tmp_path: Path):
    malformed = tmp_path / "broken.txt"
    malformed.write_text("not-json", encoding="utf-8")
    controller = PlaybackController()
    controller.countdown = 0
    error_spy = QSignalSpy(controller.error)
    with qtbot.waitSignal(controller.finished, timeout=2000):
        assert controller.play(Song(malformed, "Broken"))
    assert len(error_spy) == 1
    assert controller.state == "error"
    assert not controller.busy


def test_controller_emits_countdown_then_playing(qtbot, monkeypatch, tmp_path: Path):
    sheet = tmp_path / "valid.txt"
    sheet.write_text(json.dumps({"songNotes": [{"time": 0, "key": "1Key0"}]}))

    class FakePlayer:
        def __init__(self, **kwargs):
            self.input_guard = kwargs.get("input_guard")

        def play_events(self, events, stop, pause, countdown, **kwargs):
            assert countdown == 0
            return True

    monkeypatch.setattr(playback_module, "MacroPlayer", FakePlayer)
    controller = PlaybackController()
    controller.countdown = 1
    states = []
    controller.state_changed.connect(states.append)
    with qtbot.waitSignal(controller.finished, timeout=2500):
        assert controller.play(Song(sheet, "Valid"))
    assert states[0] == "countdown"
    assert "playing" in states
    assert states[-1] == "idle"


def test_controller_can_replace_completed_qthread_safely(qtbot, monkeypatch, tmp_path: Path):
    sheet = tmp_path / "valid.txt"
    sheet.write_text(json.dumps({"songNotes": [{"time": 0, "key": "1Key0"}]}))

    class FakePlayer:
        def __init__(self, **kwargs):
            pass

        def play_events(self, events, stop, pause, countdown, **kwargs):
            return True

    monkeypatch.setattr(playback_module, "MacroPlayer", FakePlayer)
    controller = PlaybackController()
    controller.countdown = 0
    song = Song(sheet, "Valid")
    with qtbot.waitSignal(controller.finished, timeout=2000):
        assert controller.play(song)
    assert not controller.busy
    with qtbot.waitSignal(controller.finished, timeout=2000):
        assert controller.play(song)
    assert not controller.busy


def test_late_playback_started_does_not_override_stopping_state() -> None:
    controller = PlaybackController()
    controller._active_session = 4
    controller._stop.set()
    controller._set_state("stopping")
    controller._apply_playback_started(4)
    assert controller.state == "stopping"


@pytest.mark.parametrize("raw, expected", [
    ("F9", "<f9>"), ("Ctrl+Right", "<ctrl>+<right>"), ("1", "1"),
])
def test_hotkey_canonicalization(raw, expected):
    assert canonical_hotkey(raw) == expected
