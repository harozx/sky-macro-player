import json
from pathlib import Path

import pytest

from macro_player.domain import CURRENT_SETTINGS_VERSION, FavoriteEntry, Settings
from macro_player.paths import migrate_legacy_user_data
from macro_player.repositories import (
    FavoritesRepository,
    JsonDataError,
    SettingsRepository,
    SheetRepository,
    UnsafePathError,
    ValidationError,
)


def test_settings_defaults_when_file_is_missing(tmp_path: Path) -> None:
    assert SettingsRepository(tmp_path / "settings.json").load() == Settings()


def test_settings_migrates_legacy_names_and_saves_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"countdown": 5, "alpha": 0.75, "topmost": False, "shortcuts": {"play": "f8"}}),
        encoding="utf-8",
    )
    repository = SettingsRepository(path)
    settings = repository.load()
    assert settings.countdown_seconds == 5
    assert settings.window_opacity == 0.75
    assert settings.hotkeys == {"play": "f8"}

    repository.save(settings)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == CURRENT_SETTINGS_VERSION
    assert "alpha" not in saved


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"countdown_seconds": True}, "countdown_seconds"),
        ({"window_opacity": 0.1}, "window_opacity"),
        ({"hotkeys": []}, "hotkeys"),
    ],
)
def test_settings_rejects_invalid_values(tmp_path: Path, payload: object, field: str) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match=field):
        SettingsRepository(path).load()


def test_atomic_save_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    SettingsRepository(path).save(Settings(countdown_seconds=7))
    assert json.loads(path.read_text(encoding="utf-8"))["countdown_seconds"] == 7
    assert list(tmp_path.glob("*.tmp")) == []


def test_runtime_data_migration_copies_once_without_overwrite(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    data = tmp_path / "user-data"
    legacy.mkdir()
    (legacy / "hotkeys.json").write_text('{"old": true}', encoding="utf-8")
    (legacy / "favorites.json").write_text('[]', encoding="utf-8")
    copied = migrate_legacy_user_data(data_dir=data, legacy_dirs=(legacy,))
    assert {path.name for path in copied} == {"hotkeys.json", "favorites.json"}
    (legacy / "hotkeys.json").write_text('{"new": true}', encoding="utf-8")
    assert migrate_legacy_user_data(data_dir=data, legacy_dirs=(legacy,)) == ()
    assert (data / "hotkeys.json").read_text(encoding="utf-8") == '{"old": true}'


def test_favorites_migrates_list_deduplicates_and_normalizes(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    favorites_file = tmp_path / "favorites.json"
    favorites_file.write_text(json.dumps(["Album\\Song.json", "Album/Song.json"]), encoding="utf-8")
    assert FavoritesRepository(favorites_file, sheets).load() == (
        FavoriteEntry(name="Song.json", path="Album/Song.json"),
    )


def test_favorites_migrates_existing_object_shape_and_sheet_prefix(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    favorites_file = tmp_path / "favorites.json"
    favorites_file.write_text(
        json.dumps([{"name": "Song", "type": "JSON", "path": "sheets\\Song.txt"}]),
        encoding="utf-8",
    )
    assert FavoritesRepository(favorites_file, sheets).load() == (
        FavoriteEntry(name="Song", path="Song.txt"),
    )


def test_favorites_rejects_paths_outside_sheet_root(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    repository = FavoritesRepository(tmp_path / "favorites.json", sheets)
    with pytest.raises(UnsafePathError):
        repository.save(["../secret.json"])


def test_sheet_loads_single_notes_and_chords(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    (sheets / "song.json").write_text(
        json.dumps(
            {
                "name": "Example",
                "artist": "Someone",
                "songNotes": [
                    {"time": 0, "key": "1Key0"},
                    {"time": 1.25, "key": ["1Key1", "2Key1"]},
                ],
            }
        ),
        encoding="utf-8",
    )
    sheet = SheetRepository(sheets).load("song.json")
    assert sheet.title == "Example"
    assert sheet.notes[0].keys == ("1Key0",)
    assert sheet.notes[1].keys == ("1Key1", "2Key1")
    assert sheet.metadata["artist"] == "Someone"


def test_sheet_loads_existing_one_item_list_txt_format(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    (sheets / "legacy.txt").write_text(
        json.dumps([{"name": "Legacy", "songNotes": [{"time": 10, "key": "1Key0"}]}]),
        encoding="utf-8",
    )
    assert SheetRepository(sheets).load("legacy.txt").title == "Legacy"


def test_sheet_rejects_bad_json_with_useful_location(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    (sheets / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(JsonDataError, match="line 1"):
        SheetRepository(sheets).load("bad.json")


def test_sheet_rejects_out_of_order_notes(tmp_path: Path) -> None:
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    (sheets / "bad.json").write_text(
        json.dumps({"songNotes": [{"time": 2, "key": "1Key0"}, {"time": 1, "key": "1Key1"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match=r"songNotes\[1\]\.time"):
        SheetRepository(sheets).load("bad.json")
