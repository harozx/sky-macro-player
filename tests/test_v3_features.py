"""v3 features: engine timing controls, library policies/import, user data, UI flows."""

import json
import threading
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent

from macro_player import paths
from macro_player.diagnostics import build_report, redacted_settings
from macro_player.domain import (
    CURRENT_SETTINGS_VERSION,
    HistoryEntry,
    LibraryState,
    Settings,
    SongPreference,
)
from macro_player.engine import MacroPlayer
from macro_player.hotkeys import conflicts_with_music_keys
from macro_player.library import Library, Song, apply_layer_policy, is_layered
from macro_player.repositories import (
    LibraryStateRepository,
    SettingsRepository,
    SheetRepository,
    ValidationError,
)
from macro_player.ui.dialogs import CommandPalette, OnboardingWizard
from macro_player.ui.main_window import MainWindow
from macro_player.ui.widgets import HotkeyEdit, KeyGrid, NoteRunway, hotkey_from_event
from macro_player.window_focus import WindowInfo, choose_target_window, pickable_windows
from tests.test_engine import FakeClock, RecordingController, player, sheet


# ---------------------------------------------------------------- engine
def test_speed_scales_note_spacing():
    clock = FakeClock()
    controller = RecordingController(clock)
    subject = player(clock, controller, key_hold_sec=0, speed=2.0)
    assert subject.play_json_sheet(sheet((0, "1Key0"), (200, "1Key1")),
                                   threading.Event(), countdown_sec=0)
    assert [stamp for _, stamp in controller.pressed] == pytest.approx([0, .1])


def test_speed_change_mid_song_rebases_without_skipping():
    holder = {"speed": 1.0}

    def hook(clock):
        if clock.now >= .1:
            holder["speed"] = .5

    class Speed:
        def __float__(self):
            return holder["speed"]

    clock = FakeClock(hook)
    controller = RecordingController(clock)
    subject = player(clock, controller, key_hold_sec=0, speed=Speed())
    assert subject.play_json_sheet(sheet((0, "1Key0"), (200, "1Key1")),
                                   threading.Event(), countdown_sec=0)
    # 100 ms of song at 1x, the remaining 100 ms at 0.5x takes 200 ms.
    assert controller.pressed[1][1] == pytest.approx(.3, abs=.011)


def test_start_and_end_positions_limit_the_played_section():
    clock = FakeClock()
    controller = RecordingController(clock)
    subject = player(clock, controller, key_hold_sec=0)
    events = [(0, ("1Key0",)), (100, ("1Key1",)), (200, ("1Key2",)), (300, ("1Key3",))]
    assert subject.play_events(events, threading.Event(), start_ms=100, end_ms=250)
    assert [key for key, _ in controller.pressed] == ["u", "i"]
    assert [stamp for _, stamp in controller.pressed] == pytest.approx([0, .1])
    # Waits until B (250 ms) so a loop keeps its rhythm.
    assert clock.now == pytest.approx(.15)


def test_key_callback_and_duplicate_chord_keys_are_pressed_once():
    clock = FakeClock()
    controller = RecordingController(clock)
    seen = []
    subject = player(clock, controller, key_hold_sec=0, key_callback=seen.append)
    assert subject.play_events([(0, ("1Key0", "1Key0", "1Key1"))], threading.Event())
    assert [key for key, _ in controller.pressed] == ["y", "u"]
    assert seen == [("y", "u")]


def test_custom_layout_requires_fifteen_distinct_keys():
    assert MacroPlayer.layout_map(list("abcdefghijklmno"))["1Key14"] == "o"
    with pytest.raises(ValueError):
        MacroPlayer.layout_map(list("abc"))
    with pytest.raises(ValueError):
        MacroPlayer.layout_map(list("aacdefghijklmno"))


# --------------------------------------------------------------- library
def write_sheet(folder: Path, name: str, notes, title=None) -> Path:
    path = folder / name
    data = {"songNotes": [{"time": t, "key": k} for t, k in notes]}
    if title:
        data["name"] = title
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_layer_policies_never_change_sheet_silently(tmp_path: Path):
    write_sheet(
        tmp_path, "layered.json", [(0, "1Key0"), (10, "2Key0"), (10, "1Key1"), (20, "3Key4")]
    )
    parsed = SheetRepository(tmp_path).load("layered.json")
    assert is_layered(parsed)
    assert [keys for _, keys in apply_layer_policy(parsed, None)] == [
        ("1Key0",), ("2Key0",), ("1Key1",), ("3Key4",)
    ]
    merged = apply_layer_policy(parsed, "merge")
    assert [keys for _, keys in merged] == [("1Key0",), ("1Key0",), ("1Key1",), ("1Key4",)]
    layer1 = apply_layer_policy(parsed, "layer1")
    assert [keys for _, keys in layer1] == [("1Key0",), ("1Key1",)]


def test_library_scan_applies_policy_and_reports_metadata(tmp_path: Path):
    write_sheet(tmp_path, "layered.json", [(0, "1Key0"), (2000, "2Key1")], title="Nhiều lớp")
    library = Library(tmp_path, tmp_path / "fav.json")
    keys = [f"1Key{i}" for i in range(15)]
    [blocked] = library.scan(keys)
    assert not blocked.playable and blocked.layered
    assert blocked.title == "Nhiều lớp" and blocked.duration_ms == 2000 and blocked.note_count == 2
    [merged] = library.scan(keys, {"layered.json": "merge"})
    assert merged.playable
    events, moments, duration = library.prepare("layered.json", keys, "merge")
    assert duration == 2000 and moments == [0, 2000]


def test_library_reloads_sheet_when_file_changes(tmp_path: Path):
    path = write_sheet(tmp_path, "song.json", [(0, "1Key0")])
    library = Library(tmp_path, tmp_path / "fav.json")
    assert len(library.load("song.json").notes) == 1
    write_sheet(tmp_path, "song.json", [(0, "1Key0"), (10, "1Key1"), (20, "1Key2")])
    import os
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 10_000_000))
    assert len(library.load("song.json").notes) == 3


def test_import_validates_renames_and_never_touches_source(tmp_path: Path):
    root, outside = tmp_path / "lib", tmp_path / "outside"
    outside.mkdir()
    library = Library(root, tmp_path / "fav.json")
    write_sheet(root, "song.json", [(0, "1Key0")])
    good = write_sheet(outside, "song.json", [(0, "1Key1"), (500, "1Key2")])
    bad = outside / "broken.txt"
    bad.write_text("not json", encoding="utf-8")
    original = good.read_bytes()
    candidate = library.inspect_import(good)
    assert candidate.valid and candidate.conflict and candidate.note_count == 2
    assert not library.inspect_import(bad).valid
    assert library.import_file(candidate, "skip") is None
    renamed = library.import_file(candidate, "rename")
    assert renamed.name == "song (2).json"
    assert library.import_file(library.inspect_import(bad)) is None
    assert good.read_bytes() == original
    overwritten = library.import_file(candidate, "overwrite")
    assert overwritten.read_bytes() == original


def test_song_difficulty_from_note_density():
    assert Song(Path("a"), "a", duration_ms=10_000, note_count=20).difficulty == "Dễ"
    assert Song(Path("a"), "a", duration_ms=10_000, note_count=40).difficulty == "Vừa"
    assert Song(Path("a"), "a", duration_ms=10_000, note_count=80).difficulty == "Khó"


# ------------------------------------------------------------- user data
def test_seed_copies_new_bundled_sheets_once_and_respects_deletions(tmp_path: Path):
    source, target = tmp_path / "bundled", tmp_path / "user"
    source.mkdir()
    write_sheet(source, "a.json", [(0, "1Key0")])
    assert [p.name for p in paths.seed_user_sheets(source, target)] == ["a.json"]
    (target / "a.json").unlink()
    write_sheet(source, "b.json", [(0, "1Key0")])
    assert [p.name for p in paths.seed_user_sheets(source, target)] == ["b.json"]
    assert not (target / "a.json").exists()
    assert SheetRepository(target).list() == ("b.json",)


def test_settings_v4_round_trip_and_v3_upgrade(tmp_path: Path):
    repository = SettingsRepository(tmp_path / "s.json")
    expected = Settings(keyboard_layout="custom", custom_layout_keys=tuple("abcdefghijklmno"),
                        speed=1.2, minimize_to_tray=True, preview_sound=False,
                        focus_target_exe="Heartopia.exe", mini_position=(10, 20),
                        first_run_completed=True)
    repository.save(expected)
    assert repository.load() == expected
    (tmp_path / "v3.json").write_text(json.dumps({"schema_version": 3}), encoding="utf-8")
    upgraded = SettingsRepository(tmp_path / "v3.json").load()
    assert upgraded.first_run_completed is True
    assert upgraded.schema_version == CURRENT_SETTINGS_VERSION
    assert SettingsRepository(tmp_path / "missing.json").load().first_run_completed is False


@pytest.mark.parametrize("payload", [
    {"keyboard_layout": "custom"},
    {"custom_layout_keys": list("aab")},
    {"focus_target_exe": "C:\\Games\\x.exe"},
    {"speed": 9},
])
def test_settings_v4_rejects_invalid_values(tmp_path: Path, payload):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError):
        SettingsRepository(path).load()


def test_library_state_round_trip_and_validation(tmp_path: Path):
    repository = LibraryStateRepository(tmp_path / "state.json")
    state = LibraryState(
        history=(HistoryEntry("a.txt", 5.0),), play_counts={"a.txt": 3},
        preferences={"a.txt": SongPreference(speed=.8, layer_policy="merge")},
        playlists={"Tối": ("a.txt", "b.txt")})
    repository.save(state)
    assert repository.load() == state
    (tmp_path / "bad.json").write_text(json.dumps({"preferences": {"a": {"layer_policy": "x"}}}))
    with pytest.raises(ValidationError):
        LibraryStateRepository(tmp_path / "bad.json").load()


def test_diagnostics_redact_hotkeys_and_include_logs(tmp_path: Path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("hello", encoding="utf-8")
    settings = Settings(hotkeys={"stop": "f10"}, pause_hotkey="f9")
    assert redacted_settings(settings)["hotkeys"] == {"stop": "<redacted>"}
    report = build_report(tmp_path / "r.zip", settings=settings,
                          library_summary={"songs": 1}, log_dir=logs)
    with zipfile.ZipFile(report) as archive:
        names = set(archive.namelist())
        text = archive.read("settings.json").decode("utf-8")
    assert {"info.json", "settings.json", "library.json", "logs/app.log"} <= names
    assert "f10" not in text and "f9" not in text


# ----------------------------------------------------------- focus/hotkey
def test_custom_target_window_matches_exe_only():
    windows = [WindowInfo(1, "Heartopia", 10, r"C:\G\Heartopia.exe"),
               WindowInfo(2, "Notes", 11, r"C:\W\notepad.exe"),
               WindowInfo(3, "", 12, r"C:\G\Heartopia.exe")]
    assert choose_target_window(windows, "heartopia.exe").handle == 1
    assert choose_target_window(windows, "sky.exe") is None
    assert [w.handle for w in pickable_windows(windows)] == [1, 2]


def test_bare_music_key_cannot_be_a_global_hotkey():
    assert conflicts_with_music_keys("Y", "yuiop")
    assert not conflicts_with_music_keys("Ctrl+Y", "yuiop")
    assert not conflicts_with_music_keys("F9", "yuiop")


def test_hotkey_from_event_formats_combinations():
    ctrl_shift = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    assert hotkey_from_event(Qt.Key.Key_F8, ctrl_shift) == "Ctrl+Shift+F8"
    assert hotkey_from_event(Qt.Key.Key_A, Qt.KeyboardModifier.AltModifier) == "Alt+A"
    assert hotkey_from_event(Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier) == "Esc"
    assert hotkey_from_event(Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier) is None


def test_hotkey_edit_records_pressed_keys(qtbot):
    edit = HotkeyEdit("F9")
    qtbot.addWidget(edit)
    qtbot.keyClick(edit, Qt.Key.Key_F7, Qt.KeyboardModifier.ControlModifier)
    assert edit.text() == "Ctrl+F7"
    qtbot.keyClick(edit, Qt.Key.Key_Backspace)
    assert edit.text() == ""


# --------------------------------------------------------------- widgets
def test_key_grid_lights_played_keys(qtbot):
    grid = KeyGrid()
    qtbot.addWidget(grid)
    grid.set_labels(list("yuiophjkl;nm,./"))
    grid.flash(["y", ";"])
    assert grid.lit_labels() == ["y", ";"]
    qtbot.waitUntil(lambda: grid.lit_labels() == [], timeout=1000)


def test_runway_maps_click_to_song_position(qtbot):
    runway = NoteRunway()
    qtbot.addWidget(runway)
    runway.resize(500, 74)
    runway.set_timeline([0, 5000, 10000], 10000)
    _, playhead, _ = runway._geometry()
    assert runway.position_at(playhead) == 0
    assert runway.position_at(10_000) == 10000


# ---------------------------------------------------------------- window
class FakeController:
    def __init__(self):
        self.busy = False
        self.state = "idle"
        self.played = []
        self.preview = False
        self.speed = 1.0
        self.start_ms = 0
        self.loop_range = None

    def stop(self):
        self.state = "stopping"

    def play(self, song):
        self.played.append((song, self.preview, self.speed, self.start_ms, self.loop_range))
        return True


@pytest.fixture
def window(qtbot, tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    write_sheet(root, "alpha.json", [(0, "1Key0"), (3000, "1Key1"), (6000, "1Key2")], "Alpha")
    write_sheet(root, "layered.json", [(0, "1Key0"), (100, "2Key1")], "Layered")
    library = Library(root, tmp_path / "fav.json")
    win = MainWindow(enable_global_hotkeys=False, use_tray=False, library=library)
    qtbot.addWidget(win)
    win.settings_repository = SettingsRepository(tmp_path / "settings.json")
    win.state_repository = LibraryStateRepository(tmp_path / "state.json")
    win.library_state = LibraryState()
    win.settings = replace(win.settings, focus_lock_enabled=False)
    win.controller = FakeController()
    return win


def song_named(win, title):
    return next(song for song in win.songs if song.title == title)


def test_layer_policy_unblocks_layered_song_and_is_remembered(window):
    layered = song_named(window, "Layered")
    assert not layered.playable
    assert not window.play_song(layered)
    window.set_layer_policy(layered, "merge")
    assert song_named(window, "Layered").playable
    assert window.state_repository.load().preferences["layered.json"].layer_policy == "merge"
    assert window.play_song(song_named(window, "Layered"))


def test_history_and_play_counts_are_recorded_for_real_playback_only(window):
    alpha = song_named(window, "Alpha")
    window._session_preview = True
    window._record_play(alpha)
    assert window.library_state.play_counts == {}
    window._session_preview = False
    window._record_play(alpha)
    window._record_play(alpha)
    state = window.state_repository.load()
    assert state.play_counts["alpha.json"] == 2
    assert state.history[0].path == "alpha.json" and len(state.history) == 1
    assert song_named(window, "Alpha").play_count == 2


def test_speed_is_remembered_per_song_and_applied(window):
    alpha = song_named(window, "Alpha")
    window.library_page.select_song(alpha)
    window.set_speed(0.8)
    assert window.library_state.preferences["alpha.json"].speed == 0.8
    window.play_song(alpha)
    assert window.controller.played[-1][2] == 0.8


def test_cursor_and_ab_loop_are_passed_to_the_session(window):
    alpha = song_named(window, "Alpha")
    window.library_page.select_song(alpha)
    window.set_cursor(3000)
    window.play_song(alpha)
    assert window.controller.played[-1][3] == 3000
    window.set_cursor(1000)
    window.set_loop_mark("a")
    window.set_cursor(5000)
    window.set_loop_mark("b")
    window.play_song(alpha)
    assert window.controller.played[-1][4] == (1000, 5000)
    window.clear_loop()
    window.play_song(alpha)
    assert window.controller.played[-1][3:] == (0, None)


def test_too_short_ab_loop_is_rejected(window):
    alpha = song_named(window, "Alpha")
    window.library_page.select_song(alpha)
    window.set_cursor(1000)
    window.set_loop_mark("a")
    window.set_cursor(1200)
    window.set_loop_mark("b")
    assert window.loop_marks["b"] is None


def test_preview_mode_skips_focus_lock_and_is_flagged(window):
    window.settings = replace(window.settings, focus_lock_enabled=True)

    class NoGame:
        def find_sky_window(self):
            return None

    window.focus_service = NoGame()
    alpha = song_named(window, "Alpha")
    assert not window.play_song(alpha)
    window.dock.preview_button.setChecked(True)
    assert window.preview_mode
    assert window.play_song(alpha)
    assert window.controller.played[-1][1] is True


def test_preview_mode_cannot_change_while_busy(window):
    window.controller.busy = True
    window.dock.preview_button.setChecked(True)
    assert not window.preview_mode
    assert not window.dock.preview_button.isChecked()


def test_playlists_save_load_and_report_missing(window):
    alpha = song_named(window, "Alpha")
    window.queue.add_song(alpha)
    assert window.save_playlist("Tối nay")
    window.queue.clear()
    playlists = dict(window.library_state.playlists)
    playlists["Cũ"] = ("alpha.json", "deleted.json")
    window._save_state(replace(window.library_state, playlists=playlists))
    assert window.load_playlist("Cũ")
    assert [song.title for song in window.queue.songs()] == ["Alpha"]
    assert "không còn" in window.dock.status.text()
    window.delete_playlist("Cũ")
    assert "Cũ" not in window.state_repository.load().playlists


def test_import_adds_songs_and_selects_first(window, tmp_path):
    outside = tmp_path / "drop"
    outside.mkdir()
    write_sheet(outside, "new song.json", [(0, "1Key3")], "Bài mới")
    (outside / "notes.md").write_text("ignored", encoding="utf-8")
    imported = window.import_paths([outside], action="rename", confirm=False)
    assert [path.name for path in imported] == ["new song.json"]
    assert window.library_page.selected_song().title == "Bài mới"
    assert "Đã nhập 1 bài" in window.dock.status.text()


def test_custom_layout_is_validated_and_applied(window):
    window._save_custom_layout("abc")
    assert window.settings.keyboard_layout != "custom"
    assert "15" in window.dock.status.text()
    window._save_custom_layout("qwertasdfgzxcvb")
    assert window.settings.keyboard_layout == "custom"
    assert window._key_map()["1Key0"] == "q"
    assert window.key_grid._labels[0] == "q"


def test_focus_target_can_be_changed_and_reset(window):
    window._set_target_exe("Heartopia.exe")
    assert window.settings.focus_target_exe == "Heartopia.exe"
    assert "Heartopia.exe" in window.settings_page.target_label.text()
    window._set_target_exe("Sky.exe")
    assert window.settings.focus_target_exe is None


def test_export_diagnostics_writes_zip(window, tmp_path):
    report = window.export_diagnostics(tmp_path / "diag.zip")
    with zipfile.ZipFile(report) as archive:
        library = json.loads(archive.read("library.json"))
    assert library["songs"] == 2 and library["playable"] == 1


def test_minimize_to_tray_hides_instead_of_closing(window):
    class Tray:
        notified = []

        def notify(self, *args):
            self.notified.append(args)

        def hide(self):
            pass

    window.tray = Tray()
    window.settings = replace(window.settings, minimize_to_tray=True)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and not window._closing
    window._quitting = True
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted() and window._closing


def test_onboarding_values_and_completion_flag(window, qtbot):
    wizard = OnboardingWizard(layout_name="new", focus_lock=False, stop_key="f10",
                              pause_key="f9", next_key="f11", test_window=lambda: "ok")
    qtbot.addWidget(wizard)
    assert wizard.values() == {"keyboard_layout": "new", "focus_lock_enabled": False}
    wizard.focus_lock.setChecked(True)
    for _ in range(3):
        wizard.next_button.click()
    assert wizard.result() == wizard.DialogCode.Accepted
    assert wizard.values()["focus_lock_enabled"] is True


def test_command_palette_finds_songs_and_commands(qtbot):
    ran = []
    songs = [Song(Path("bang.txt"), "Bâng khuâng")]
    palette = CommandPalette(songs, [("Dừng", lambda: ran.append("stop"))])
    qtbot.addWidget(palette)
    chosen = []
    palette.song_chosen.connect(chosen.append)
    palette.input.setText("bang")
    assert palette.list.count() == 1
    palette._run_current()
    assert chosen == songs
    palette.input.setText("dung")
    palette._run_current()
    assert ran == ["stop"]


def test_play_next_on_empty_queue_explains(window):
    window.play_next()
    assert "trống" in window.dock.status.text()


def test_queue_complete_status(window):
    window.current_song = song_named(window, "Alpha")
    window._session_from_queue = True
    window._playback_finished(True)
    assert "hết hàng chờ" in window.dock.status.text()


# ------------------------------------------------ real worker, no OS input
def test_preview_session_runs_on_worker_without_os_keyboard(qtbot, tmp_path, monkeypatch):
    from macro_player.playback import PlaybackController

    def forbidden(*args, **kwargs):
        raise AssertionError("preview must not create an OS keyboard controller")

    monkeypatch.setattr("macro_player.engine.keyboard.Controller", forbidden)
    path = write_sheet(tmp_path, "short.json", [(0, "1Key0"), (30, "1Key1"), (60, "1Key2")])
    controller = PlaybackController()
    controller.countdown = 0
    controller.preview = True
    pressed = []
    started = []
    controller.keys_pressed.connect(pressed.append)
    controller.playback_started.connect(started.append)
    with qtbot.waitSignal(controller.finished, timeout=3000) as blocker:
        assert controller.play(Song(path, "Short"))
    assert blocker.args == [True]
    assert pressed == [["y"], ["u"], ["i"]]
    assert len(started) == 1


def test_loop_session_repeats_until_stop(qtbot, tmp_path, monkeypatch):
    from macro_player.playback import PlaybackController

    monkeypatch.setattr("macro_player.engine.keyboard.Controller",
                        lambda: (_ for _ in ()).throw(AssertionError("no OS keyboard")))
    path = write_sheet(tmp_path, "loop.json", [(0, "1Key0"), (20, "1Key1"), (500, "1Key2")])
    controller = PlaybackController()
    controller.countdown = 0
    controller.preview = True
    controller.loop_range = (0, 40)
    pressed = []
    controller.keys_pressed.connect(pressed.append)
    with qtbot.waitSignal(controller.finished, timeout=3000) as blocker:
        assert controller.play(Song(path, "Loop"))
        qtbot.waitUntil(lambda: len(pressed) >= 6, timeout=2000)
        controller.stop()
    assert blocker.args == [False]
    assert ["i"] not in pressed
    assert pressed[:4] == [["y"], ["u"], ["y"], ["u"]]


# ---------------------------------------------------------------- updates
def test_version_comparison():
    from macro_player.updates import is_newer, parse_version
    assert parse_version("v3.0.1") == (3, 0, 1)
    assert is_newer("v3.0.0", "2.1.0")
    assert not is_newer("v2.1.0", "2.1.0")
    assert not is_newer("garbage", "2.1.0")


def test_update_checker_parses_release_payload(qtbot):
    from macro_player.updates import RELEASES_PAGE, UpdateChecker
    checker = UpdateChecker()
    found, failed = [], []
    checker.update_available.connect(lambda tag, url: found.append((tag, url)))
    checker.failed.connect(failed.append)
    checker.handle_payload(json.dumps({"tag_name": "v99.0.0",
                                       "html_url": "https://evil.example/x"}).encode())
    assert found == [("v99.0.0", RELEASES_PAGE)]
    checker.handle_payload(b"{")
    assert failed
