"""Property-based tests: the sheet parser and sheet edits hold their invariants."""

import json
import math
import threading

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from macro_player.engine import MacroPlayer
from macro_player.repositories import RepositoryError, SheetRepository
from macro_player.sheet_tools import (
    EditOptions,
    apply_edits,
    change_tempo,
    cut,
    merge_layers,
    normalize,
    quantize,
    transpose,
)
from tests.test_macro_core import FakeClock, RecordingController

KEYS = [f"{layer}Key{index}" for layer in (1, 2, 3) for index in range(15)]
times = st.integers(min_value=0, max_value=600_000)
chords = st.lists(st.sampled_from(KEYS), min_size=1, max_size=4)
events_strategy = st.lists(st.tuples(times, chords), min_size=1, max_size=60).map(
    lambda items: normalize((float(t), tuple(k)) for t, k in items))
fast = settings(max_examples=80, deadline=None,
                suppress_health_check=[HealthCheck.function_scoped_fixture])


def all_keys(events):
    return [key for _, keys in events for key in keys]


# ------------------------------------------------------------------ parser
json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=True) | st.text(max_size=8),
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=12,
)


@fast
@given(payload=json_values | st.fixed_dictionaries({"songNotes": json_values}))
def test_parser_never_crashes_on_arbitrary_json(payload, tmp_path_factory):
    folder = tmp_path_factory.mktemp("sheets")
    (folder / "x.json").write_text(json.dumps(payload), encoding="utf-8")
    try:
        sheet = SheetRepository(folder).load("x.json")
    except RepositoryError:
        return
    # Anything accepted is safe to play: finite, ordered, non-empty string keys.
    stamps = [note.time for note in sheet.notes]
    assert all(math.isfinite(stamp) and stamp >= 0 for stamp in stamps)
    assert stamps == sorted(stamps)
    assert all(key and isinstance(key, str) for note in sheet.notes for key in note.keys)


@fast
@given(events=events_strategy)
def test_valid_sheets_round_trip_through_the_parser(events, tmp_path_factory):
    folder = tmp_path_factory.mktemp("sheets")
    payload = [{"name": "t", "songNotes": [{"time": t, "key": k} for t, keys in events
                                           for k in keys]}]
    (folder / "s.json").write_text(json.dumps(payload), encoding="utf-8")
    sheet = SheetRepository(folder).load("s.json")
    assert normalize((note.time, note.keys) for note in sheet.notes) == events


# ------------------------------------------------------------------- edits
@fast
@given(events=events_strategy)
def test_normalize_is_idempotent_and_sorted(events):
    again = normalize(events)
    assert again == events
    stamps = [time for time, _ in events]
    assert stamps == sorted(set(stamps))
    assert all(len(keys) == len(set(keys)) for _, keys in events)


@fast
@given(events=events_strategy)
def test_merge_layers_leaves_only_layer_one(events):
    merged = merge_layers(events)
    assert all(key.startswith("1Key") for key in all_keys(merged))
    assert {time for time, _ in merged} == {time for time, _ in events}


@fast
@given(events=events_strategy, steps=st.integers(-7, 7))
def test_transpose_stays_inside_fifteen_keys(events, steps):
    shifted, _ = transpose(events, steps)
    for key in all_keys(shifted):
        assert 0 <= int(key.split("Key")[1]) < 15
    assert [time for time, _ in shifted] == [time for time, _ in events]


@fast
@given(events=events_strategy, steps=st.integers(-6, 6))
def test_transpose_without_folding_is_reversible(events, steps):
    shifted, folded = transpose(events, steps)
    if folded == 0:
        back, _ = transpose(shifted, -steps)
        assert back == events


@fast
@given(events=events_strategy, step=st.integers(20, 2000))
def test_quantized_notes_sit_on_the_grid(events, step):
    snapped, _ = quantize(events, step)
    origin = events[0][0]
    for time, _ in snapped:
        assert abs((time - origin) / step - round((time - origin) / step)) * step <= 1
    assert set(all_keys(snapped)) == set(all_keys(events))


@fast
@given(events=events_strategy, percent=st.integers(50, 200))
def test_tempo_scales_length_and_keeps_order(events, percent):
    changed = change_tempo(events, percent)
    assert set(all_keys(changed)) == set(all_keys(events))
    assert changed[-1][0] == round(events[-1][0] * 100 / percent) or len(changed) < len(events)


@fast
@given(events=events_strategy, start=times, length=st.integers(0, 600_000))
def test_cut_keeps_only_the_section(events, start, length):
    end = start + length
    section = cut(events, start, end)
    inside = [item for item in events if start <= item[0] <= end]
    assert len(section) == len(inside)
    if section:
        assert section[0][0] == 0


@fast
@given(events=events_strategy, steps=st.integers(-7, 7), percent=st.integers(50, 200),
       step=st.one_of(st.none(), st.integers(20, 1000)))
def test_merged_edits_are_always_playable(events, steps, percent, step):
    result, report = apply_edits(events, EditOptions(
        merge_layers=True, quantize_step_ms=step, transpose_steps=steps, tempo_percent=percent))
    assert not report.layered_left
    clock = FakeClock()
    player = MacroPlayer(controller=RecordingController(clock), clock=clock, sleep=clock.sleep,
                         key_hold_sec=0, poll_interval_sec=60)
    assert player.play_events(result, threading.Event())
