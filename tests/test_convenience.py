"""Library search/sort/filter, play-all, shuffle and repeat behaviour."""

import random
from pathlib import Path

import pytest

from macro_player.library import Song
from macro_player.search import fold_text, matches
from macro_player.ui.library_page import LibraryPage, sort_songs
from macro_player.ui.main_window import MainWindow
from macro_player.ui.queue_panel import QueuePanel
from macro_player.ui.widgets import format_duration


class FakeController:
    def __init__(self):
        self.busy = False
        self.state = "idle"
        self.played = []

    def stop(self):
        self.state = "stopping"

    def play(self, song):
        self.played.append(song)
        return True


def song(name, **kwargs):
    return Song(Path(f"{name}.txt"), name, **kwargs)


@pytest.mark.parametrize("raw, expected", [
    ("Bâng khuâng", "bang khuang"),
    ("Đi để trở về", "di de tro ve"),
    ("Bất nhiễm  (Fin)", "bat nhiem fin"),
    ("Lần đầu tiên", "lan dau tien"),
    ("千本桜", "千本桜"),
])
def test_fold_text_removes_vietnamese_accents(raw, expected):
    assert fold_text(raw) == expected


@pytest.mark.parametrize("query", ["bang khuang", "BÂNG", "khuang bang", "bangkhuang", ""])
def test_matches_ignores_accents_case_order_and_spaces(query):
    assert matches(query, "Bâng khuâng")


def test_matches_rejects_missing_words():
    assert not matches("bang xyz", "Bâng khuâng")


def test_library_search_finds_title_without_accents(qtbot):
    page = LibraryPage([song("Bâng khuâng"), song("Đi để trở về")])
    qtbot.addWidget(page)
    page.search.setText("di de")
    assert [s.title for s in page.visible_songs()] == ["Đi để trở về"]


def test_library_empty_state_replaces_list_when_nothing_matches(qtbot):
    page = LibraryPage([song("Alpha")])
    qtbot.addWidget(page)
    page.search.setText("zzz")
    assert page.empty_state.isVisibleTo(page)
    assert "zzz" in page.empty_state.text()
    assert not page.list.isVisibleTo(page)
    assert not page.play_all_button.isEnabled()
    page.search.clear()
    assert page.list.isVisibleTo(page)
    assert page.result_count.text() == "Hiển thị 1/1"


def test_library_reports_empty_library(qtbot):
    page = LibraryPage([])
    qtbot.addWidget(page)
    assert "trống" in page.empty_state.text()


def test_playable_filter_hides_unsupported_sheets(qtbot):
    page = LibraryPage([song("Good"), song("Layered", playable=False)])
    qtbot.addWidget(page)
    next(b for b in page.filters.buttons() if b.key == "playable").click()
    assert [s.title for s in page.visible_songs()] == ["Good"]
    assert "Không hỗ trợ" in LibraryPage.item_text(song("Layered", playable=False))


def test_sort_options_and_selection_is_kept(qtbot):
    songs = [song("Bê", duration_ms=9000, added_at=1),
             song("An", duration_ms=3000, added_at=3),
             song("Ca", duration_ms=6000, added_at=2)]
    assert [s.title for s in sort_songs(songs, "title")] == ["An", "Bê", "Ca"]
    assert [s.title for s in sort_songs(songs, "title_desc")] == ["Ca", "Bê", "An"]
    assert [s.title for s in sort_songs(songs, "shortest")] == ["An", "Ca", "Bê"]
    assert [s.title for s in sort_songs(songs, "longest")] == ["Bê", "Ca", "An"]
    assert [s.title for s in sort_songs(songs, "newest")] == ["An", "Ca", "Bê"]

    page = LibraryPage(songs)
    qtbot.addWidget(page)
    page.list.setCurrentRow(2)
    selected = page.selected_song()
    page.sort.setCurrentIndex(page.sort.findData("longest"))
    assert page.selected_song() == selected
    assert page.visible_songs()[0].title == "Bê"


def test_format_duration():
    assert format_duration(0) == "0:00"
    assert format_duration(185_400) == "3:05"


def test_real_library_has_metadata_and_flags_unsupported_sheets(qtbot):
    window = MainWindow(enable_global_hotkeys=False, use_tray=False)
    qtbot.addWidget(window)
    songs = window.songs
    assert all(not s.title.endswith("Không hỗ trợ") for s in songs)
    assert sum(not s.playable for s in songs) == 6
    assert all(s.duration_ms > 0 and s.note_count > 0 for s in songs if s.playable)


def test_queue_replace_clear_and_undo(qtbot):
    queue = QueuePanel()
    qtbot.addWidget(queue)
    queue.add_song(song("Old"))
    queue.replace_songs([song("A"), song("B")])
    assert [s.title for s in queue.songs()] == ["A", "B"]
    assert queue.undo_button.isVisibleTo(queue)
    queue.undo()
    assert [s.title for s in queue.songs()] == ["Old"]
    queue.clear()
    assert queue.songs() == []
    queue.undo()
    assert [s.title for s in queue.songs()] == ["Old"]
    assert not queue.undo_button.isVisibleTo(queue)


def test_queue_shuffle_keeps_all_songs(qtbot):
    queue = QueuePanel()
    qtbot.addWidget(queue)
    items = [song(str(i)) for i in range(10)]
    for item in items:
        queue.add_song(item)
    queue.shuffle(random.Random(4))
    assert sorted(s.title for s in queue.songs()) == sorted(s.title for s in items)
    assert queue.songs() != items


def test_repeat_mode_cycles(qtbot):
    queue = QueuePanel()
    qtbot.addWidget(queue)
    labels = []
    for _ in range(3):
        queue.cycle_repeat()
        labels.append((queue.repeat_mode, queue.repeat_button.text()))
    assert labels == [("all", "Lặp: Hàng chờ"), ("one", "Lặp: Một bài"), ("off", "Lặp: Tắt")]
    with pytest.raises(ValueError):
        queue.set_repeat_mode("forever")


@pytest.fixture
def window(qtbot):
    win = MainWindow(enable_global_hotkeys=False, use_tray=False)
    qtbot.addWidget(win)
    win.controller = FakeController()
    win.play_song = lambda s: bool(win.controller.play(s))
    return win


def test_play_all_skips_unsupported_and_queues_the_rest(window):
    songs = [song("A"), song("Bad", playable=False), song("B"), song("C")]
    assert window.play_all(songs)
    assert [s.title for s in window.controller.played] == ["A"]
    assert [s.title for s in window.queue.songs()] == ["B", "C"]


def test_play_all_shuffle_is_seeded_and_complete(window):
    window._rng = random.Random(1)
    songs = [song(str(i)) for i in range(8)]
    assert window.play_all(songs, shuffle=True)
    played = window.controller.played + window.queue.songs()
    assert sorted(s.title for s in played) == sorted(s.title for s in songs)
    assert played != songs


def test_play_all_rejects_list_without_playable_songs(window):
    assert not window.play_all([song("Bad", playable=False)])
    assert window.controller.played == []


def test_repeat_one_replays_finished_song(window, qtbot):
    current = song("Loop")
    window.current_song = current
    window.queue.add_song(song("Next"))
    window.queue.set_repeat_mode("one")
    window._playback_finished(completed=True)
    qtbot.waitUntil(lambda: window.controller.played == [current])
    assert [s.title for s in window.queue.songs()] == ["Next"]


def test_repeat_all_moves_finished_song_to_queue_end(window, qtbot):
    window.current_song = song("A")
    window.queue.add_song(song("B"))
    window.queue.set_repeat_mode("all")
    window._playback_finished(completed=True)
    qtbot.waitUntil(lambda: window.controller.played == [song("B")])
    assert [s.title for s in window.queue.songs()] == ["A"]


@pytest.mark.parametrize("mode", ["one", "all"])
def test_stop_never_triggers_repeat(window, qtbot, mode):
    window.current_song = song("A")
    window.queue.set_repeat_mode(mode)
    window._playback_finished(completed=False)
    qtbot.wait(20)
    assert window.controller.played == []
    assert window.queue.songs() == []


def test_stop_cancels_scheduled_repeat(window, qtbot):
    window.current_song = song("A")
    window.queue.set_repeat_mode("one")
    window._playback_finished(completed=True)
    window.stop_playback()
    qtbot.wait(20)
    assert window.controller.played == []
