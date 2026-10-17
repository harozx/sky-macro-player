"""VI/EN interface: catalog coverage, language setting and an English window."""

import ast
import re
import string
from pathlib import Path

import pytest

from macro_player import i18n, paths
from macro_player.domain import CURRENT_SETTINGS_VERSION, Settings
from macro_player.i18n_en import EN
from macro_player.library import Library
from macro_player.repositories import SettingsRepository, ValidationError

PACKAGE = Path(__file__).resolve().parents[1] / "macro_player"
NON_ASCII = re.compile(r"[^\x00-\x7f]")
# Accented Latin letters; symbols such as × · → are fine in English text.
VIETNAMESE_LETTER = re.compile(r"[À-ÖØ-öø-ɏḀ-ỿ]")
# Non-ASCII literals that are symbols, not words, and need no translation.
UNTRANSLATED = {"♪", "×", "  ·  ", " · ", "đ"}


def _sources():
    return sorted(path for path in PACKAGE.rglob("*.py") if not path.name.startswith("i18n"))


def _marked_strings():
    """(location, text) for every literal passed to tr() or N_()."""
    found = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in {"tr", "N_"} and node.args):
                arg = node.args[0]
                location = f"{path.name}:{node.lineno}"
                assert not isinstance(arg, ast.JoinedStr), (
                    f"{location}: pass a template to tr() and call .format() on the result")
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.append((location, arg.value))
    return found


def _fields(text):
    return {field for _, field, _, _ in string.Formatter().parse(text) if field is not None}


@pytest.fixture
def english():
    i18n.set_language("en")
    yield
    i18n.set_language("vi")


def test_every_marked_string_has_an_english_entry():
    marked = _marked_strings()
    assert len(marked) > 300
    missing = [f"{location}: {text!r}" for location, text in marked if text not in EN]
    assert not missing, "\n".join(missing)


def test_english_entries_keep_the_same_placeholders():
    for source, english in EN.items():
        assert _fields(source) == _fields(english), source
        assert not VIETNAMESE_LETTER.search(english), english


def test_catalog_has_no_unused_entries():
    used = {text for _, text in _marked_strings()}
    assert set(EN) - used == set()


def test_no_vietnamese_literal_escapes_translation():
    """A new UI string written without tr() would stay Vietnamese in English mode."""
    leaks = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        wrapped = set()
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in {"tr", "N_"}:
                wrapped.update(id(child) for child in ast.walk(node))
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                docstrings.add(id(node.value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and NON_ASCII.search(node.value) and id(node) not in wrapped
                    and id(node) not in docstrings and node.value not in UNTRANSLATED):
                leaks.append(f"{path.name}:{node.lineno}: {node.value!r}")
    assert not leaks, "\n".join(leaks)


def test_tr_defaults_to_vietnamese_and_switches_to_english(english):
    assert i18n.tr("Thư viện") == "Library"
    assert i18n.tr("Không tìm thấy sheet '{relative}'.").format(relative="a.json") \
        == "Sheet 'a.json' was not found."
    assert i18n.tr("chuỗi chưa dịch") == "chuỗi chưa dịch"
    i18n.set_language("vi")
    assert i18n.tr("Thư viện") == "Thư viện"
    i18n.set_language("xx")
    assert i18n.language() == "vi"


# --------------------------------------------------------------- settings
def test_language_defaults_to_vietnamese(tmp_path):
    assert Settings().language == "vi"
    path = tmp_path / "settings.json"
    path.write_text('{"schema_version": 4}', encoding="utf-8")
    assert SettingsRepository(path).load().language == "vi"


def test_language_round_trips_without_changing_schema(tmp_path):
    repository = SettingsRepository(tmp_path / "settings.json")
    repository.save(Settings(language="en"))
    loaded = repository.load()
    assert loaded.language == "en"
    assert loaded.schema_version == CURRENT_SETTINGS_VERSION == 4
    assert '"language": "en"' in (tmp_path / "settings.json").read_text(encoding="utf-8")


def test_unknown_language_is_rejected(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"language": "fr"}', encoding="utf-8")
    with pytest.raises(ValidationError) as error:
        SettingsRepository(path).load()
    assert error.value.field == "language"


# --------------------------------------------------------------- window
def _window(qtbot, tmp_path, monkeypatch, language):
    from macro_player.ui.main_window import MainWindow

    settings_file = tmp_path / "settings.json"
    SettingsRepository(settings_file).save(Settings(language=language, first_run_completed=True))
    monkeypatch.setattr(paths, "settings_file", lambda: settings_file)
    sheets = tmp_path / "sheets"
    sheets.mkdir()
    library = Library(sheets, tmp_path / "favorites.json")
    win = MainWindow(enable_global_hotkeys=False, use_tray=False, library=library)
    qtbot.addWidget(win)
    return win


def test_window_is_vietnamese_by_default(qtbot, tmp_path, monkeypatch):
    win = _window(qtbot, tmp_path, monkeypatch, "vi")
    assert [button.text() for button in win.nav_buttons] == ["Thư viện", "Phím tắt", "Cài đặt"]
    assert win.settings_page.language.currentData() == "vi"
    assert win.dock.play_button.text() == "Phát"


def test_window_is_english_after_restart(qtbot, tmp_path, monkeypatch):
    win = _window(qtbot, tmp_path, monkeypatch, "en")
    try:
        assert [button.text() for button in win.nav_buttons] == ["Library", "Hotkeys", "Settings"]
        assert win.settings_page.language.currentData() == "en"
        assert win.dock.play_button.text() == "Play"
        assert win.settings_page.key_layout.itemText(0) == "Old layout (yuiophjkl;nm,./)"
        assert win.mini.status.text() == "Ready"
    finally:
        i18n.set_language("vi")


def test_changing_language_saves_and_asks_for_restart(qtbot, tmp_path, monkeypatch):
    win = _window(qtbot, tmp_path, monkeypatch, "vi")
    combo = win.settings_page.language
    combo.setCurrentIndex(combo.findData("en"))
    assert win.settings.language == "en"
    assert SettingsRepository(paths.settings_file()).load().language == "en"
    assert "Mở lại ứng dụng" in win.dock.status.text()
    # The running window keeps its language until restart.
    assert win.nav_buttons[0].text() == "Thư viện"
    assert i18n.language() == "vi"
