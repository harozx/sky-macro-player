"""Text sheets ("sheet chữ") and batch processing of downloaded folders."""

import json
import random
from dataclasses import replace

import pytest

from macro_player.batch import analyze, classify_timing, collect_files, position_fit
from macro_player.domain import LibraryState
from macro_player.engine import MacroPlayer
from macro_player.library import Library
from macro_player.repositories import LibraryStateRepository, SettingsRepository
from macro_player.sheet_tools import normalize
from macro_player.text_sheet import detect_format, parse_text_sheet
from macro_player.ui.main_window import MainWindow
from macro_player.ui.text_import import BatchDialog, TextSheetDialog

OLD = MacroPlayer.KEY_LAYOUTS["old"]["json_map"]
NEW = MacroPlayer.KEY_LAYOUTS["new"]["json_map"]
KEYS = [f"1Key{i}" for i in range(15)]


def codes(sheet):
    return [keys for _, keys in sheet.events]


# --------------------------------------------------------------- notation
@pytest.mark.parametrize("text, fmt", [
    ("1 2 3 5 6 1'", "number"),
    ("Đô Rê Mi Son La Đô'", "solfege"),
    ("do re mi sol la ti", "solfege"),
    ("y u i o p h j", "keys"),
])
def test_format_detection(text, fmt):
    assert detect_format(text) == fmt


def test_numbers_octaves_chords_and_rests():
    sheet = parse_text_sheet("1 2 - 3 | (1 3 5) 1' 2'' 0 5,", step_ms=100)
    assert codes(sheet) == [("1Key0",), ("1Key1",), ("1Key2",), ("1Key0", "1Key2", "1Key4"),
                            ("1Key7",), ("1Key8",), ("1Key4",)]
    assert [time for time, _ in sheet.events] == [0, 100, 300, 400, 500, 600, 800]
    assert sheet.folded == 2 and not sheet.issues


def test_base_octave_moves_note_one_to_the_middle():
    sheet = parse_text_sheet("1 7 1'", step_ms=100, base_octave=1)
    assert codes(sheet) == [("1Key7",), ("1Key13",), ("1Key14",)]


def test_solfege_ignores_accents_and_case():
    sheet = parse_text_sheet("ĐÔ rê Mi FA Sol la Si Đô'", step_ms=100)
    assert codes(sheet) == [(f"1Key{i}",) for i in range(8)]


def test_key_letters_follow_the_chosen_layout():
    old = parse_text_sheet("y u [yi] - /", fmt="keys", step_ms=100, key_map=OLD)
    assert codes(old) == [("1Key0",), ("1Key1",), ("1Key0", "1Key2"), ("1Key14",)]
    new = parse_text_sheet("a s d", fmt="keys", step_ms=100, key_map=NEW)
    assert codes(new) == [("1Key0",), ("1Key1",), ("1Key2",)]


def test_line_rests_and_problems_are_reported_with_position():
    sheet = parse_text_sheet("1 2\n3 x (5", step_ms=100, line_rest_steps=2)
    assert [time for time, _ in sheet.events] == [0, 100, 400]
    messages = [(issue.line, issue.column, issue.token) for issue in sheet.issues]
    assert (2, 3, "x") in messages and (2, 5, "(") in messages
    assert "Dòng 2" in sheet.issues[0].describe()


def test_unknown_key_letter_is_reported():
    sheet = parse_text_sheet("y q", fmt="keys", step_ms=100, key_map=OLD)
    assert codes(sheet) == [("1Key0",)] and sheet.issues[0].token == "q"


def test_unknown_format_is_rejected():
    with pytest.raises(ValueError):
        parse_text_sheet("1", fmt="morse")


# ------------------------------------------------------------------ batch
def jittered(seed, beat=250):
    rng = random.Random(seed)
    base = [i * beat for i in range(32)] + [32 * beat + beat // 2]
    return normalize([(t + (rng.randint(-8, 8) if t else 0), ("1Key0",)) for t in base]), base


def test_jitter_is_recognised_and_snapped_back_exactly():
    for seed in range(10):
        events, base = jittered(seed)
        kind, grid = classify_timing(events)
        assert kind == "jitter", seed
        from macro_player.sheet_tools import quantize
        snapped, _ = quantize(events, grid.step_ms)
        assert [time for time, _ in snapped] == base


def test_exact_unclear_and_short_timing():
    exact = normalize((i * 200.0, ("1Key0",)) for i in range(20))
    assert classify_timing(exact)[0] == "exact"
    rng = random.Random(3)
    messy = normalize((float(sum(rng.randint(90, 700) for _ in range(i))), ("1Key0",))
                      for i in range(30))
    assert classify_timing(messy)[0] == "unclear"
    assert classify_timing(exact[:3])[0] == "short"
    assert position_fit(exact, 200, 3) == 1


def messy_notes(rng):
    """Strictly increasing times with no common beat."""
    time, notes = 0, []
    for _ in range(30):
        notes.append((time, "1Key4"))
        time += rng.randint(90, 700)
    return notes


def write(folder, name, notes):
    path = folder / name
    path.write_text(json.dumps({"name": name, "songNotes": [
        {"time": t, "key": k} for t, k in notes]}), encoding="utf-8")
    return path


def test_analyze_folder_classifies_each_file(tmp_path):
    folder = tmp_path / "downloads"
    folder.mkdir()
    (folder / "sub").mkdir()
    write(folder, "clean.json", [(i * 300, "1Key1") for i in range(10)])
    write(folder, "layered.json", [(i * 300, "2Key3") for i in range(10)])
    events, _ = jittered(1)
    write(folder / "sub", "hand.json", [(t, "1Key2") for t, _ in events])
    (folder / "broken.txt").write_text("1 2 3 5", encoding="utf-8")
    (folder / "notes.md").write_text("ignored", encoding="utf-8")
    assert len(collect_files([folder])) == 4
    items = {item.source.name: item for item in analyze([folder], KEYS)}
    assert items["clean.json"].status == "ok" and not items["clean.json"].changed
    assert items["layered.json"].status == "changed"
    assert items["hand.json"].status == "changed" and items["hand.json"].moved > 0
    assert items["broken.txt"].status == "error" and "sheet chữ" in items["broken.txt"].describe()
    kept = {item.source.name: item for item in analyze([folder], KEYS, merge=False,
                                                       fix_timing=False)}
    assert kept["layered.json"].status == "review"
    assert kept["hand.json"].status == "ok" and kept["hand.json"].moved == 0


# ------------------------------------------------------------------ dialogs
def test_text_dialog_previews_and_saves(qtbot):
    dialog = TextSheetDialog(dict(OLD))
    qtbot.addWidget(dialog)
    assert not dialog.save_button.isEnabled()
    dialog.text.setPlainText("1 2 3 x")
    dialog.reparse()
    assert dialog.sheet.note_count == 3 and dialog.issues.text()
    assert not dialog.save_button.isEnabled() and dialog.listen_button.isEnabled()
    dialog.ignore_issues.setChecked(True)
    assert dialog.save_button.isEnabled()
    dialog.tempo.setValue(60)
    dialog.per_beat.setCurrentIndex(dialog.per_beat.findData(2))
    dialog.reparse()
    assert dialog.sheet.events[1][0] == 500
    saved = []
    dialog.save_requested.connect(lambda name, events: saved.append((name, events)))
    dialog.name.setText("Bài thử")
    dialog.save_button.click()
    assert saved[0][0] == "Bài thử" and len(saved[0][1]) == 3


def test_batch_dialog_options_rerun_analysis(qtbot, tmp_path):
    write(tmp_path, "layered.json", [(i * 300, "2Key3") for i in range(10)])
    calls = []

    def rerun(merge, fix):
        calls.append((merge, fix))
        return analyze([tmp_path], KEYS, merge=merge, fix_timing=fix)

    dialog = BatchDialog(rerun(True, True), rerun)
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == 1 and "Thêm 1 bài" in dialog.import_button.text()
    dialog.merge.setChecked(False)
    assert calls[-1] == (False, True)
    dialog.skip_review.setChecked(True)
    assert dialog.selected_items() == [] and not dialog.import_button.isEnabled()


# ------------------------------------------------------------------- window
class FakeController:
    def __init__(self):
        self.busy = False
        self.state = "idle"
        self.countdown = 3
        self.played = []

    def stop(self):
        self.state = "stopping"

    def play(self, song):
        self.played.append(song)
        return True


@pytest.fixture
def window(qtbot, tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    win = MainWindow(enable_global_hotkeys=False, use_tray=False,
                     library=Library(root, tmp_path / "fav.json"))
    qtbot.addWidget(win)
    win.settings_repository = SettingsRepository(tmp_path / "settings.json")
    win.state_repository = LibraryStateRepository(tmp_path / "state.json")
    win.library_state = LibraryState()
    win.settings = replace(win.settings, focus_lock_enabled=False)
    win.controller = FakeController()
    return win


def test_text_import_saves_playable_song(window):
    dialog = window.open_text_import()
    dialog.text.setPlainText("Đô Rê Mi Son La")
    dialog.reparse()
    dialog.listen_button.click()
    assert window.controller.played and window.controller.countdown == 0
    window._playback_finished(True)
    dialog.name.setText("Năm nốt")
    dialog.save_button.click()
    song = window.library_page.selected_song()
    assert song.title == "Năm nốt" and song.playable and song.note_count == 5
    dialog.reject()


def test_batch_process_imports_and_can_be_undone(window, tmp_path):
    folder = tmp_path / "downloads"
    folder.mkdir()
    original = write(folder, "layered.json", [(i * 300, "2Key3") for i in range(10)])
    before = original.read_bytes()
    write(folder, "clean.json", [(i * 300, "1Key1") for i in range(10)])
    rng = random.Random(2)
    write(folder, "messy.json", messy_notes(rng))
    added = window.batch_process([folder], confirm=False)
    assert sorted(path.name for path in added) == ["clean.json", "layered.json", "messy.json"]
    assert original.read_bytes() == before
    layered = next(song for song in window.songs if song.relative == "layered.json")
    assert layered.playable
    assert "nên nghe thử lại" in window.dock.status.text()
    assert window.undo_last_import() == (3, 0)
    assert window.songs == []


def test_batch_process_can_skip_songs_to_check(window, tmp_path):
    folder = tmp_path / "downloads2"
    folder.mkdir()
    rng = random.Random(2)
    write(folder, "messy.json", messy_notes(rng))
    assert window.batch_process([folder], confirm=False, skip_review=True) == []


def test_batch_process_empty_folder_explains(window, tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    assert window.batch_process([empty], confirm=False) == []
    assert ".txt/.json" in window.dock.status.text()


def test_bundled_public_domain_sheets_are_playable_and_on_grid(tmp_path):
    from macro_player.paths import bundled_sheets_dir
    library = Library(bundled_sheets_dir(), tmp_path / "fav.json")
    authored = [song for song in library.scan(KEYS)
                if "public domain" in str(library.load(song.relative).metadata.get("author"))]
    assert len(authored) == 7
    for song in authored:
        events = normalize((n.time, n.keys) for n in library.load(song.relative).notes)
        assert song.playable, song.title
        assert classify_timing(events)[0] == "exact", song.title
