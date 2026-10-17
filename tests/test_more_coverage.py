"""Behaviour not covered elsewhere: startup, sound, Win32 focus, dialogs, window states."""

import json
import threading
import wave
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent, QMouseEvent

from macro_player import app as app_module
from macro_player.domain import LibraryState, Settings
from macro_player.library import ImportCandidate, Library, Song
from macro_player.playback import NullKeyboard, PlaybackWorker, SpeedRef
from macro_player.repositories import LibraryStateRepository, SettingsRepository
from macro_player.ui import sound
from macro_player.ui.dialogs import CommandPalette, ImportDialog, WindowPickerDialog
from macro_player.ui.main_window import MainWindow
from macro_player.ui.tray import TrayController, app_icon
from macro_player.ui.widgets import HotkeyEdit, NoteRunway
from macro_player.updates import UpdateChecker
from macro_player.window_focus import WindowInfo, WindowsFocusService


# ------------------------------------------------------------------ startup
def test_version_flag_prints_without_starting_qt(capsys):
    assert app_module.main(["app", "--version"]) == 0
    assert capsys.readouterr().out.strip() == app_module.__version__


def test_smoke_test_builds_and_closes_the_real_window(qapp, capsys):
    assert app_module.smoke_test(qapp) == 0
    assert "smoke-test ok" in capsys.readouterr().out


# -------------------------------------------------------------------- sound
def test_tones_are_generated_once_as_valid_wav(tmp_path):
    paths = sound.ensure_tones(tmp_path)
    assert len(paths) == 15
    with wave.open(str(paths[0])) as handle:
        assert handle.getframerate() == sound.SAMPLE_RATE and handle.getnframes() > 1000
    stamp = paths[0].stat().st_mtime_ns
    sound.ensure_tones(tmp_path)
    assert paths[0].stat().st_mtime_ns == stamp


def test_preview_synth_tolerates_out_of_range_indices(qapp, tmp_path):
    synth = sound.PreviewSynth(tmp_path)
    synth.play_indices([0, 99, -1])
    assert synth.available in (True, False)


# ------------------------------------------------------------- Win32 focus
def test_windows_focus_service_is_read_only_safe():
    service = WindowsFocusService()
    windows = service.windows()
    assert all(isinstance(window, WindowInfo) for window in windows)
    bogus = WindowInfo(0x7FFFFFF0, "Sky", 999_999, r"C:\nowhere\Sky.exe")
    assert service.validate_target(bogus) is False
    assert service.activate(bogus) is False
    assert service.is_foreground(bogus) is False
    assert service.is_window(bogus) is False
    service.target_exe = "definitely-not-running.exe"
    assert service.find_sky_window() is None


# ------------------------------------------------------------------ worker
def test_worker_runs_synchronously_in_preview(qapp, tmp_path):
    path = tmp_path / "w.json"
    path.write_text(json.dumps({"songNotes": [{"time": 0, "key": "1Key0"},
                                              {"time": 10, "key": "1Key1"}]}))
    events = [(0.0, ("1Key0",)), (10.0, ("1Key1",))]
    worker = PlaybackWorker(
        Song(path, "w"), loader=lambda song: (events, [0, 10], 10),
        key_map={f"1Key{i}": "yuiophjkl;nm,./"[i] for i in range(15)},
        stop=threading.Event(), pause=threading.Event(), countdown=0,
        session=7, speed=SpeedRef(2.0), preview=True)
    seen = {"keys": [], "progress": [], "done": []}
    worker.keys_pressed.connect(lambda session, keys: seen["keys"].append(keys))
    worker.progress.connect(lambda session, ms: seen["progress"].append(ms))
    worker.completed.connect(seen["done"].append)
    worker.run()
    assert seen["keys"] == [["y"], ["u"]] and seen["done"] == [True]
    assert seen["progress"][-1] == 10
    NullKeyboard().press("y")
    NullKeyboard().release("y")


def test_worker_reports_loader_errors(qapp):
    def broken(song):
        raise ValueError("bad sheet")

    worker = PlaybackWorker(Song(Path("x"), "x"), loader=broken, key_map={},
                            stop=threading.Event(), pause=threading.Event(), countdown=0)
    failures = []
    worker.failed.connect(failures.append)
    worker.run()
    assert failures == ["bad sheet"]


def test_worker_countdown_respects_stop(qapp):
    stop = threading.Event()
    stop.set()
    worker = PlaybackWorker(Song(Path("x"), "x"), loader=lambda s: ([], [], 0), key_map={},
                            stop=stop, pause=threading.Event(), countdown=5)
    results = []
    worker.completed.connect(results.append)
    worker.run()
    assert results == [False]


# ------------------------------------------------------------------ dialogs
def test_import_dialog_reports_each_file_and_conflict_choice(qtbot):
    candidates = [ImportCandidate(Path("a.txt"), "a.txt", "A", 3, 1000),
                  ImportCandidate(Path("b.txt"), "b.txt", error="broken"),
                  ImportCandidate(Path("c.txt"), "c.txt", "C", 2, 500, layered=True, conflict=True)]
    dialog = ImportDialog(candidates)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 3
    assert "Lỗi" in dialog.table.item(1, 1).text()
    assert dialog.conflict.isEnabled() and dialog.conflict_action == "rename"
    assert dialog.import_button.text() == "Nhập 2 bài"


def test_window_picker_returns_executable(qtbot):
    dialog = WindowPickerDialog([WindowInfo(1, "Heartopia", 2, r"C:\G\Heartopia.exe")])
    qtbot.addWidget(dialog)
    assert dialog.selected_exe() is None
    dialog.list.setCurrentRow(0)
    assert dialog.selected_exe() == "Heartopia.exe"
    empty = WindowPickerDialog([])
    qtbot.addWidget(empty)
    empty.list.setCurrentRow(0)
    assert empty.selected_exe() is None


def test_command_palette_keyboard_navigation(qtbot):
    palette = CommandPalette([], [("Dừng", lambda: None), ("Đổi chế độ lặp", lambda: None)])
    qtbot.addWidget(palette)
    assert palette.list.currentRow() == 0
    palette._move(1)
    assert palette.list.currentRow() == 1
    palette._move(1)
    assert palette.list.currentRow() == 0


# ---------------------------------------------------------- tray, widgets
def test_tray_menu_and_status(qtbot):
    tray = TrayController()
    shown = []
    tray.show_requested.connect(lambda: shown.append(True))
    tray.set_status("Bài", "Đang phát")
    assert "Bài" in tray.icon.toolTip()
    tray._activated(tray.icon.ActivationReason.Trigger)
    assert shown == [True]
    tray.notify("t", "m")
    assert not app_icon().isNull()
    assert len(tray.menu.actions()) >= 6


def test_runway_click_emits_position_and_paints_markers(qtbot):
    runway = NoteRunway()
    qtbot.addWidget(runway)
    runway.resize(600, 80)
    runway.set_timeline([0, 1000, 2000], 2000)
    runway.loop_a, runway.loop_b, runway.cursor_ms = 200, 1500, 800
    assert not runway.grab().isNull()
    clicked = []
    runway.position_clicked.connect(clicked.append)
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(300, 40), QPointF(300, 40),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    runway.mousePressEvent(event)
    assert clicked == []
    runway.seekable = True
    runway.mousePressEvent(event)
    assert len(clicked) == 1 and 0 <= clicked[0] <= 2000
    runway.set_playing(True)
    runway.set_speed(1.5)
    runway.set_reduced_motion(False)
    assert runway.elapsed >= 0
    runway.reset()


def test_hotkey_edit_lets_tab_move_focus(qtbot):
    edit = HotkeyEdit("F9")
    qtbot.addWidget(edit)
    qtbot.keyClick(edit, Qt.Key.Key_Tab)
    assert edit.text() == "F9"
    qtbot.keyClick(edit, Qt.Key.Key_Shift)
    assert edit.text() == "F9"


def test_update_checker_reports_up_to_date(qtbot):
    checker = UpdateChecker()
    calls = []
    checker.up_to_date.connect(lambda: calls.append("ok"))
    checker.handle_payload(json.dumps({"tag_name": "v0.0.1"}).encode())
    assert calls == ["ok"]
    checker.handle_payload(json.dumps({"no_tag": True}).encode())


# ------------------------------------------------------------------ window
class FakeController:
    def __init__(self):
        self.busy = False
        self.state = "idle"
        self.countdown = 3
        self.played = []
        self.stopped = 0
        self.paused = 0

    def stop(self):
        self.stopped += 1
        self.state = "stopping"

    def play(self, song):
        self.played.append(song)
        return True

    def toggle_pause(self):
        self.paused += 1


@pytest.fixture
def window(qtbot, tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    for name, title in (("a.json", "Alpha"), ("b.json", "Beta")):
        (root / name).write_text(json.dumps({"name": title, "songNotes": [
            {"time": 0, "key": "1Key0"}, {"time": 900, "key": "1Key1"}]}), encoding="utf-8")
    win = MainWindow(enable_global_hotkeys=False, use_tray=False,
                     library=Library(root, tmp_path / "fav.json"))
    qtbot.addWidget(win)
    win.settings_repository = SettingsRepository(tmp_path / "settings.json")
    win.state_repository = LibraryStateRepository(tmp_path / "state.json")
    win.library_state = LibraryState()
    win.settings = replace(win.settings, focus_lock_enabled=False)
    win.controller = FakeController()
    return win


def test_settings_controls_save_and_apply(window):
    page = window.settings_page
    page.countdown.setValue(7)
    assert window.settings.countdown_seconds == 7 and window.controller.countdown == 7
    page.reduced_motion.setChecked(True)
    assert window.settings.reduced_motion
    page.always_on_top.setChecked(False)
    assert not window.settings.always_on_top and not window.mini.pin_button.isChecked()
    page.minimize_to_tray.setChecked(True)
    page.preview_sound.setChecked(False)
    page.check_updates.setChecked(True)
    saved = window.settings_repository.load()
    assert saved.minimize_to_tray and not saved.preview_sound and saved.check_updates
    page.key_layout.setCurrentIndex(page.key_layout.findData("new"))
    assert window.settings.keyboard_layout == "new" and window._key_map()["1Key0"] == "a"
    page.key_layout.setCurrentIndex(page.key_layout.findData("custom"))
    assert window.settings.keyboard_layout == "new"
    assert "15 phím" in window.dock.status.text()
    page.resume_focus_checkbox.setChecked(False)
    assert not window.settings.resume_on_sky_focus
    page.focus_lock_checkbox.setChecked(True)
    assert window.settings.focus_lock_enabled


def test_failed_save_restores_widgets(window):
    class Broken:
        def save(self, settings):
            from macro_player.repositories import RepositoryError
            raise RepositoryError("disk full")

    window.settings_repository = Broken()
    window.settings_page.reduced_motion.setChecked(True)
    assert not window.settings_page.reduced_motion.isChecked()
    assert "disk full" in window.dock.status.text()


def test_state_changes_update_dock_mini_and_labels(window):
    window.current_song = window.songs[0]
    for state, expected in (("countdown", "Đang đếm ngược"), ("playing", "Đang phát"),
                            ("paused", "Đã tạm dừng"), ("error", "Có lỗi phát nhạc")):
        window._state_changed(state)
        assert window.mini.status.text() == expected
    window._state_changed("focus_paused")
    assert window.dock.play_button.text() == "Trở lại game"
    window._countdown_status(2)
    assert "2 giây" in window.dock.status.text()
    window._session_preview = True
    window._state_changed("playing")
    assert "Xem trước" in window.dock.status.text()
    window._progress_status(500)
    window._keys_pressed(["y"])


def test_toggle_play_routes_by_state(window):
    window.controller.state = "playing"
    window.toggle_play()
    assert window.controller.paused == 1
    window.controller.state = "idle"
    window.library_page.list.setCurrentRow(-1)
    window.library_page.list.clearSelection()
    window.current_song = None
    window.library_page.list.setCurrentItem(None)
    window.queue.add_song(window.songs[1])
    window.toggle_play()
    assert window.controller.played[-1] == window.songs[1]
    assert window.queue.songs() == []


def test_focus_paused_resume_requires_game(window):
    window.controller.state = "focus_paused"
    window.active_sky_window = None
    window.toggle_play()
    assert "chọn cửa sổ game" in window.dock.status.text()


def test_song_slots_resolve_identity_and_report_problems(window):
    window.settings = replace(window.settings, song_slots=("a.json", "missing.json") + (None,) * 6)
    window._play_slot(0)
    assert window.controller.played[-1].title == "Alpha"
    window._play_slot(1)
    assert "Không tìm thấy" in window.dock.status.text()
    window._play_slot(5)
    window._play_slot(99)


def test_mini_toggle_remembers_position(window, qtbot):
    window.toggle_mini()
    assert window.mini.isVisible()
    window._mini_position = (40, 50)
    window.toggle_mini()
    assert not window.mini.isVisible()
    assert window.settings_repository.load().mini_position == (40, 50)
    window._expand_from_mini()


def test_drag_and_drop_accepts_sheets_only(window, tmp_path, qtbot):
    sheet = tmp_path / "drop.json"
    sheet.write_text(json.dumps({"songNotes": [{"time": 0, "key": "1Key2"}]}), encoding="utf-8")
    for path, accepted in ((sheet, True), (tmp_path / "notes.md", False)):
        data = QMimeData()
        data.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDragEnterEvent(QPoint(5, 5), Qt.DropAction.CopyAction, data,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.dragEnterEvent(event)
        assert event.isAccepted() is accepted
    imported = []
    window.import_paths = lambda paths, **kwargs: imported.append(paths)
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(sheet))])
    drop = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, data,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    window.dropEvent(drop)
    qtbot.waitUntil(lambda: imported == [[sheet]], timeout=1000)


def test_close_while_busy_waits_for_safe_stop(window, qtbot):
    window.controller.busy = True
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted() and window.close_pending
    assert window.controller.stopped == 1
    window.controller.busy = False
    window._playback_finished(False)
    qtbot.waitUntil(lambda: not window.close_pending, timeout=1000)


def test_narrow_window_hides_runway_controls(window, qtbot):
    window.show()
    window.resize(780, 560)
    qtbot.waitUntil(lambda: not window.dock.a_button.isVisible(), timeout=1000)
    window.resize(1200, 760)
    qtbot.waitUntil(lambda: window.dock.a_button.isVisible(), timeout=1000)


def test_import_with_nothing_to_import_explains(window, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert window.import_paths([empty], confirm=False) == []
    assert ".txt/.json" in window.dock.status.text()


def test_settings_error_is_recovered_on_next_save(window, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    window.settings_error = "broken"
    window.settings_page.countdown.setValue(4)
    assert window.settings_error is None
    assert list(tmp_path.glob("settings.json.invalid*.bak"))


def test_library_summary_and_test_window(window):
    summary = window.library_summary()
    assert summary["songs"] == 2 and summary["focus_target"] == "Sky.exe"

    class NoGame:
        def find_sky_window(self):
            return None

    window.focus_service = NoGame()
    assert window._test_window()[1] == "danger"


def test_default_settings_object_is_unchanged_by_window(window):
    assert Settings().language == "vi"


# ------------------------------------------------- queue with unplayable songs
@pytest.fixture
def mixed(qtbot, tmp_path):
    root = tmp_path / "mixed"
    root.mkdir()
    for name, key in (("1-ok.json", "1Key0"), ("2-layered.json", "2Key3"),
                      ("3-ok.json", "1Key1"), ("4-layered.json", "3Key1")):
        (root / name).write_text(json.dumps({"name": name[:-5], "songNotes": [
            {"time": 0, "key": key}, {"time": 500, "key": key}]}), encoding="utf-8")
    win = MainWindow(enable_global_hotkeys=False, use_tray=False,
                     library=Library(root, tmp_path / "fav.json"))
    qtbot.addWidget(win)
    win.settings_repository = SettingsRepository(tmp_path / "settings.json")
    win.state_repository = LibraryStateRepository(tmp_path / "state.json")
    win.library_state = LibraryState()
    win.settings = replace(win.settings, focus_lock_enabled=False)
    win.controller = FakeController()
    songs = {song.title: song for song in win.songs}
    return win, songs


def test_finished_song_skips_unplayable_queue_items(mixed, qtbot):
    win, songs = mixed
    for title in ("2-layered", "3-ok", "4-layered"):
        win.queue._append(songs[title])
    win.current_song = songs["1-ok"]
    win._playback_finished(True)
    qtbot.waitUntil(lambda: win.controller.played == [songs["3-ok"]], timeout=1000)
    assert [song.title for song in win.queue.songs()] == ["4-layered"]
    assert "2-layered" in win.queue.note.text() and win.queue.note.isVisibleTo(win.queue)


def test_next_reports_when_only_unplayable_songs_remain(mixed):
    win, songs = mixed
    win.queue._append(songs["2-layered"])
    win.queue._append(songs["4-layered"])
    win.play_next()
    assert win.controller.played == [] and win.queue.songs() == []
    assert "không còn bài nào phát được" in win.dock.status.text()


def test_missing_game_window_keeps_the_queue(mixed):
    win, songs = mixed

    class NoGame:
        def find_sky_window(self):
            return None

    win.settings = replace(win.settings, focus_lock_enabled=True)
    win.focus_service = NoGame()
    win.queue._append(songs["1-ok"])
    win.play_next()
    assert [song.title for song in win.queue.songs()] == ["1-ok"]


def test_unplayable_song_is_not_added_to_queue(mixed):
    win, songs = mixed
    assert not win.add_to_queue(songs["2-layered"])
    assert win.queue.songs() == [] and "Gộp mọi lớp" in win.dock.status.text()
    assert win.add_to_queue(songs["1-ok"])
    assert [song.title for song in win.queue.songs()] == ["1-ok"]


def test_play_all_starts_with_first_playable(mixed):
    win, songs = mixed
    assert win.play_all(list(songs.values()))
    assert win.controller.played == [songs["1-ok"]]
    assert [song.title for song in win.queue.songs()] == ["3-ok"]
