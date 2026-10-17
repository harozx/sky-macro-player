# Sky Macro Player

Sky Macro Player is a Windows music-sheet player for **Sky: Children of the
Light** and **Heartopia**. Version 2 uses the PySide6 **Sky Instrument Console**
interface, an isolated Python environment, validated sheet/config repositories,
and a deterministic playback engine.

## Highlights

- Unified library with search and favorites filter.
- Queue and playback dock available from every screen.
- Mini overlay with play/pause, next, and emergency stop controls.
- Note Runway visualization tied to playback state.
- Editable global hotkeys and eight song slots.
- Optional Sky focus lock enforced inside the keyboard playback path.
- Single-instance startup so global hotkeys cannot be installed twice.
- Config migration from the previous Tkinter version.
- UTF-8 and UTF-16 `.txt`/`.json` sheet support.
- Absolute monotonic scheduling without cumulative key-hold drift.
- Per-playback cancellation events and guaranteed best-effort key release.
- Local rotating logs with hotkey values redacted.

## Install and run

Requirements: Windows 10/11 and Python 3.10 or newer.

1. Double-click `setup.bat` once. It creates `.venv` inside this folder and
   installs the pinned dependencies without Administrator rights.
2. Double-click `start.vbs` to launch without a console window.

For development:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe gui_qt.py
```

The launcher no longer downloads or installs Python globally. If Python is not
available, setup shows the official download page and exits safely.

## Using the console

- **Thư viện:** search, play, favorite, or add a song to the queue.
- **Hàng chờ:** drag to reorder, remove an item, or double-click to play it.
  On a narrow window, use **Hiện hàng chờ** in the navigation rail.
- **Phím tắt:** edit pause, stop, next, and eight song-slot bindings, then press
  **Lưu và áp dụng**.
- **Cài đặt:** choose the in-game keyboard layout, countdown, reduced motion,
  mini-player always-on-top behavior, and **Bật chế độ khóa vào cửa sổ Sky**.
- **Thu nhỏ:** opens the compact overlay while leaving playback active.

Legacy defaults remain `F10` for stop and `F11` for next. Existing slot and
pause-key assignments in `hotkeys.json` are migrated automatically.

### Sky focus lock

Enable **Bật chế độ khóa vào cửa sổ Sky** in Settings. Before playback starts,
the app finds and activates the exact Sky game window. The target is pinned by
window handle, process ID, title, and process path for that playback session. If
another window gets keyboard focus, the playback engine stops new key presses,
releases held keys, and waits safely.
Returning to Sky resumes playback when **Tự tiếp tục khi quay lại Sky** is on.
Use **Kiểm tra cửa sổ Sky** to confirm detection before playing.

Windows may occasionally prevent applications from changing the foreground
window. In that case, click Sky yourself and press Play again. The feature does
not inject input into a background game and does not bypass Windows focus rules.

The bundled library currently contains 118 structurally valid sheets: 112 are
playable with the available layouts and 6 contain unsupported `2Key*` or
`3Key*` notes. Those six are marked **Không hỗ trợ** and blocked before the
countdown. A verified mapping is still needed before those layers can be played
faithfully.

## Data and diagnostics

- Put sheet files in `sheets/`.
- User settings remain in `hotkeys.json`.
- Favorites remain in `favorites.json` and are rewritten atomically.
- Logs are written under `%LOCALAPPDATA%\SkyMacroPlayer\logs`.

Runtime data files are ignored by Git. Logs do not intentionally record pressed
keys or configured hotkey values.

## Development checks

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q macro_player *.py
```

Windows CI runs Python 3.10, 3.11, 3.12, and 3.13. The suite covers playback
timing and cancellation, focus loss inside chords, key cleanup, shutdown,
single-instance startup, malformed sheets, compatibility auditing, config
migration, atomic persistence, UI state, hotkey rollback, and logging.

## Architecture

- `macro_core.py`: validated deterministic keyboard playback.
- `macro_player/domain.py`: immutable domain models.
- `macro_player/repositories.py`: settings, favorites, and sheet persistence.
- `macro_player/logging_config.py`: privacy-conscious rotating logs and crash hooks.
- `sky_ui_core.py`: tokens, UI models, worker/controller primitives, Note Runway.
- `sky_ui_integrated.py`: repositories, settings, global hotkeys, lifecycle.
- `sky_ui_final.py`: editable hotkeys and safe application shutdown.
- `gui_qt.py`: production entry point.
- `gui.py`: preserved legacy Tkinter interface; no longer used by the launcher.

The visual and interaction contract is documented in `docs/UI_DESIGN.md`.

## License

The application source code is released under the [MIT License](LICENSE).
The music sheets in `sheets/` are community transcriptions and are **not**
covered by that license; the underlying songs may be protected by copyright
held by their original authors. Use them for personal, non-commercial play.

Automating keyboard input may be restricted by a game's terms of service.
Use the app responsibly and at your own risk.
