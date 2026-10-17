"""Sheet editor: pure transforms, dialog behaviour, saving as a new sheet."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from macro_player.domain import LibraryState
from macro_player.library import Library, Song
from macro_player.repositories import LibraryStateRepository, SettingsRepository, SheetRepository
from macro_player.sheet_tools import (
    EditOptions,
    apply_edits,
    change_tempo,
    cut,
    detect_grid,
    grid_candidates,
    merge_layers,
    normalize,
    quantize,
    save_new_sheet,
    to_sheet_payload,
    transpose,
)
from macro_player.ui.main_window import MainWindow
from macro_player.ui.sheet_editor import SheetEditorDialog


def ev(*items):
    return [(float(t), tuple(k.split("+"))) for t, k in items]


def test_merge_layers_maps_and_deduplicates():
    assert merge_layers(ev((0, "1Key0+2Key0"), (10, "3Key4"))) == ev((0, "1Key0"), (10, "1Key4"))


def test_cut_moves_section_to_start():
    events = ev((0, "1Key0"), (500, "1Key1"), (900, "1Key2"), (1500, "1Key3"))
    assert cut(events, 400, 1000) == ev((0, "1Key1"), (400, "1Key2"))


def test_quantize_snaps_to_grid_and_merges_collisions():
    events = ev((100, "1Key0"), (302, "1Key1"), (497, "1Key2"), (503, "1Key3"))
    snapped, moved = quantize(events, 200)
    assert snapped == ev((100, "1Key0"), (300, "1Key1"), (500, "1Key2+1Key3"))
    assert moved == 3


def test_transpose_steps_and_octave_folding():
    shifted, folded = transpose(ev((0, "1Key0"), (10, "1Key13")), 2)
    assert shifted == ev((0, "1Key2"), (10, "1Key8"))  # 15 folds down an octave to 8
    assert folded == 1
    down, folded = transpose(ev((0, "1Key1")), -3)
    assert down == ev((0, "1Key5")) and folded == 1


def test_change_tempo_scales_times():
    assert change_tempo(ev((0, "1Key0"), (1000, "1Key1")), 200) == ev((0, "1Key0"), (500, "1Key1"))
    assert change_tempo(ev((0, "1Key0"), (1000, "1Key1")), 50) == ev((0, "1Key0"), (2000, "1Key1"))


def test_detect_grid_prefers_coarsest_exact_subdivision():
    # Beats every 400 ms with some eighth notes at 200 ms: the beat looks off,
    # but the 200 ms subdivision explains everything and must win.
    times = [0, 400, 800, 1000, 1200, 1600, 2000, 2200, 2400]
    events = ev(*[(t, "1Key0") for t in times])
    grid = detect_grid(events)
    assert grid.step_ms == 200 and grid.on_grid == 1
    from macro_player.sheet_tools import grid_ratio
    assert grid_ratio(events, 400) < 1
    assert grid_candidates(events)[0].step_ms == 200


def test_apply_edits_pipeline_and_report():
    source = ev((0, "1Key0+2Key0"), (403, "1Key1"), (797, "1Key2"), (1200, "2Key13"))
    result, report = apply_edits(source, EditOptions(
        merge_layers=True, quantize_step_ms=400, transpose_steps=1, tempo_percent=200))
    assert result == ev((0, "1Key1"), (200, "1Key2"), (400, "1Key3"), (600, "1Key14"))
    assert report.moved == 2 and report.folded == 0 and not report.layered_left
    assert report.grid_after == 1


def test_apply_edits_warns_when_layers_remain_or_section_empty():
    _, report = apply_edits(ev((0, "2Key1")), EditOptions())
    assert report.layered_left and report.warnings
    result, report = apply_edits(ev((0, "1Key1")), EditOptions(start_ms=500, end_ms=900))
    assert result == [] and "không còn nốt" in report.warnings[0]


def test_save_new_sheet_never_overwrites_and_is_loadable(tmp_path):
    payload = to_sheet_payload("Bài: mới?", ev((0, "1Key0"), (100, "1Key1+1Key2")), source="a.txt")
    first = save_new_sheet(tmp_path, "Bài: mới?", payload)
    second = save_new_sheet(tmp_path, "Bài: mới?", payload)
    assert first.name == "Bài_ mới_.json" and second.name == "Bài_ mới_ (2).json"
    sheet = SheetRepository(tmp_path).load(first.name)
    assert [note.time for note in sheet.notes] == [0, 100, 100]
    assert sheet.metadata["editedFrom"] == "a.txt"


def test_real_sheets_round_trip_without_changes(tmp_path):
    library = Library(Path("sheets"), tmp_path / "fav.json")
    sheet = library.load("nguoiyeubolo.txt")
    source = normalize([(note.time, note.keys) for note in sheet.notes])
    result, report = apply_edits(source, EditOptions(quantize_step_ms=detect_grid(source).step_ms))
    assert result == source and report.moved == 0


# ------------------------------------------------------------------- dialog
def test_dialog_recomputes_preview_and_emits_save(qtbot):
    song = Song(Path("x.json"), "Thử")
    events = ev((0, "1Key0+2Key1"), (500, "1Key2"), (1000, "1Key3"),
                (1500, "1Key4"), (2000, "1Key5"))
    dialog = SheetEditorDialog(song, events, list("yuiophjkl;nm,./"))
    qtbot.addWidget(dialog)
    assert dialog.merge.isChecked()
    dialog.transpose.setValue(1)
    dialog.recompute()
    assert dialog.result_events()[0] == (0.0, ("1Key1", "1Key2"))
    dialog.start.setValue(1.0)
    dialog.recompute()
    assert dialog.result_events()[0][0] == 0.0 and len(dialog.result_events()) == 3
    saved = []
    dialog.save_requested.connect(lambda name, result: saved.append((name, result)))
    dialog.save_button.click()
    assert saved and saved[0][0] == "Thử (chỉnh)"
    dialog.start.setValue(2.0)
    dialog.end.setValue(1.0)
    dialog.recompute()
    assert not dialog.save_button.isEnabled()


# ------------------------------------------------------------------- window
class FakeController:
    def __init__(self):
        self.busy = False
        self.state = "idle"
        self.countdown = 3
        self.played = []
        self.preview = False

    def stop(self):
        self.state = "stopping"

    def play(self, song):
        self.played.append((song, self.preview, self.countdown))
        return True


@pytest.fixture
def window(qtbot, tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    (root / "layered.json").write_text(json.dumps({"name": "Layered", "songNotes": [
        {"time": 0, "key": "1Key0"}, {"time": 0, "key": "2Key3"},
        {"time": 410, "key": "1Key1"}, {"time": 795, "key": "2Key2"}]}), encoding="utf-8")
    win = MainWindow(enable_global_hotkeys=False, use_tray=False,
                     library=Library(root, tmp_path / "fav.json"))
    qtbot.addWidget(win)
    win.settings_repository = SettingsRepository(tmp_path / "settings.json")
    win.state_repository = LibraryStateRepository(tmp_path / "state.json")
    win.library_state = LibraryState()
    win.settings = replace(win.settings, focus_lock_enabled=False)
    win.controller = FakeController()
    return win


def test_editor_saves_playable_copy_and_keeps_original(window):
    original = (window.library.root / "layered.json").read_bytes()
    song = window.songs[0]
    assert not song.playable
    dialog = window.open_sheet_editor(song)
    dialog.quantize.setChecked(True)
    dialog.step.setValue(400)
    dialog.recompute()
    dialog.save_button.click()
    assert (window.library.root / "layered.json").read_bytes() == original
    created = window.library_page.selected_song()
    assert created.title == "Layered (chỉnh)" and created.playable
    assert window.library.load(created.relative).notes[-1].time == 800
    assert "Đã lưu" in dialog.saved_label.text()
    dialog.reject()


def test_editor_preview_uses_virtual_keyboard_without_countdown(window):
    dialog = window.open_sheet_editor(window.songs[0])
    assert dialog.listen_button.isEnabled()
    dialog.listen_button.click()
    song, preview, countdown = window.controller.played[-1]
    assert preview is True and countdown == 0
    assert window._load_for_playback(song)[2] == 795
    window._playback_finished(True)
    assert window.controller.countdown == 3 and window._preview_override is None
    dialog.reject()


def test_editor_preview_rejects_unmerged_layers(window):
    dialog = window.open_sheet_editor(window.songs[0])
    dialog.merge.setChecked(False)
    dialog.recompute()
    dialog.listen_button.click()
    assert window.controller.played == []
    assert "chưa hỗ trợ" in dialog.saved_label.text()
    dialog.reject()


def test_editor_preview_refused_while_playing(window):
    window.controller.busy = True
    assert not window.preview_events([(0.0, ("1Key0",))], "x")
    assert "dừng bài" in window.dock.status.text()
