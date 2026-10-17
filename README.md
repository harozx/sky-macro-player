# Sky Macro Player

Sky Macro Player is a Windows music-sheet player for **Sky: Children of the
Light** and **Heartopia**. It plays community sheets on the in-game instrument
through your keyboard, with a calm PySide6 "instrument console" interface, a
deterministic playback engine, and safety features that stop input as soon as
the game loses focus.

## Highlights

- **Find songs fast:** search without typing accents (`bang khuang` finds
  *Bâng khuâng*), sort by name, length, newest, most played or recently
  played, and filter All / Favorites / Playable / Recent.
- **Song details:** length, note count, notes per second with an
  Easy / Medium / Hard hint, and how many times you played it.
- **Queue and playlists:** play all, shuffle, repeat queue or one song,
  clear with undo, and save the queue as a named playlist.
- **Practice tools:** live speed 0.5×–1.5× (remembered per song), start from
  any point by clicking the Note Runway, and loop an A–B section.
- **Preview mode:** play a sheet on a virtual 15-key grid with generated
  tones. Nothing is sent to the game or any other application.
- **Add sheets in the app:** drag-and-drop `.txt`/`.json` files or folders, or
  use **Nhập sheet…** (Ctrl+O). Each file is validated first; duplicates can be
  renamed, overwritten or skipped, and **Hoàn tác nhập** undoes the last import. The library refreshes when the folder
  changes.
- **Sheet editor (Chỉnh sheet…):** merge 2Key/3Key layers, cut a section,
  snap notes to a beat grid (the grid is detected automatically, including
  eighth/sixteenth subdivisions), transpose by scale steps (notes beyond the 15
  keys fold by an octave), and change tempo. A live summary, Note Runway and
  key grid preview the result, **Nghe thử** plays it on the virtual keyboard,
  and **Lưu thành bản mới** always writes a new sheet; the original is never
  modified.
- **2Key/3Key sheets:** choose per song to merge every layer onto the 15 keys,
  play layer 1 only, or keep it blocked. Nothing is changed silently.
- **Focus lock:** playback only types into the game window. Sky is detected by
  `Sky.exe`; you can pick another game window (for example Heartopia).
- **Hotkeys:** record global shortcuts by pressing them; conflicts with the
  music keys are rejected. Eight song slots.
- **Language:** Vietnamese by default; English can be chosen in Settings
  (applies after a restart).
- **Everyday comfort:** mini player, system tray menu with notifications,
  optional close-to-tray, Ctrl+K command palette, first-run guide, custom
  15-key layout, optional update check, and a diagnostics export.

## Install

### Installer or portable build (recommended)

Download from [Releases](https://github.com/harozx/macro_project/releases):

- `SkyMacroPlayer-Setup-<version>.exe` installs for your Windows user only,
  without Administrator rights, and adds Start-menu shortcuts.
- `SkyMacroPlayer-<version>-portable.zip`: unzip anywhere and run
  `SkyMacroPlayer.exe`.

Python is not required for these builds.

### From source

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

## Using the console

- **Thư viện:** search, sort and filter; **Enter** plays the selected song,
  **Ctrl+Enter** adds it to the queue. The detail panel shows the song's
  numbers and, for layered sheets, the 2Key/3Key choice.
- **Thanh phát:** Play/Pause (Space), Next (Ctrl+→), Stop (Esc), Mini (Ctrl+M),
  speed, **A**/**B**/**Bỏ A–B**, **Xem trước** and **Bàn phím**. Click the Note
  Runway while stopped or paused to choose where playback starts.
- **Hàng chờ:** drag to reorder, double-click to play, **Trộn**, **Xóa hết**
  with **Hoàn tác**, **Lặp** (Off → Queue → One song), and **Playlist** to save,
  open or delete playlists. Stop always ends repeating.
- **Phím tắt:** click a field and press the combination. Save with
  **Lưu và áp dụng**; the previous hotkeys stay active if the new ones fail.
- **Cài đặt:** in-game layout (old, new or custom), countdown, reduced motion,
  mini player on top, close-to-tray, preview sound, focus lock and target
  window, update check, guide, diagnostics, and the data folder.
- **Bảng lệnh (Ctrl+K):** type part of a song name or a command and press Enter.

Legacy defaults remain `F10` for stop and `F11` for next.

### Focus lock

Enable **Bật chế độ khóa vào cửa sổ game** in Settings. Before playback starts
the app activates the game window and pins it by window handle, process ID and
executable path. If another window gets keyboard focus, the engine stops new key
presses, releases held keys and waits. Returning to the game resumes playback
when **Tự tiếp tục khi quay lại game** is on.

Windows may occasionally refuse to change the foreground window; click the game
yourself and press Play again. The app never injects input into a background
window and does not bypass Windows focus rules. Checking focus and sending a key
are separate Windows calls, so a key pressed in the same instant as Alt+Tab can
still reach the other window.

### Bundled sheets

118 sheets are included. 112 play with the standard layouts; 6 contain
`2Key*`/`3Key*` layers and stay blocked until you choose a layer policy for
them in the song details.

## Data and diagnostics

All user data lives in `%LOCALAPPDATA%\SkyMacroPlayer`:

- `sheets\`: your library. Bundled sheets are copied here once; a sheet you
  delete is not restored, and new bundled sheets from updates are added.
- `hotkeys.json` (settings), `favorites.json`, `library_state.json` (history,
  play counts, per-song choices, playlists), and `logs\`.

Settings and favorites from older versions (next to the app or in
`%LOCALAPPDATA%\SkyInstrumentConsole`) are copied once and never overwritten.
Unreadable files are backed up before anything new is written. Logs and
diagnostic reports do not record pressed keys or hotkey values. Uninstalling
keeps this folder.

## Development

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy macro_player
.\.venv\Scripts\python.exe -m coverage run -m pytest; .\.venv\Scripts\python.exe -m coverage report
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe packaging\build_exe.py --zip
.\dist\SkyMacroPlayer\SkyMacroPlayer.exe --smoke-test
```

Tests never touch real user data: `tests/conftest.py` points
`SKY_MACRO_DATA_DIR` at a temporary folder, and no test uses the real keyboard.
Property-based tests (hypothesis) feed random sheets to the parser and the sheet
editor. CI runs ruff, mypy and the suite with coverage (minimum 85%) on Windows
with Python 3.10–3.13, then builds the app, runs
the packaged smoke test, and builds the Inno Setup installer. Pushing a `v*`
tag publishes both files to a GitHub release.

## Architecture

- `macro_player/engine.py`: deterministic keyboard playback (speed, sections,
  focus guard, guaranteed key release). `macro_core.py` re-exports it.
- `macro_player/library.py`: sheet discovery, metadata, layer policies, import.
- `macro_player/sheet_tools.py`: pure sheet edits (layers, cut, grid, transpose,
  tempo) and saving new sheets.
- `macro_player/playback.py`: one Qt controller and worker thread per session.
- `macro_player/hotkeys.py`, `window_focus.py`: global hotkeys and focus lock.
- `macro_player/domain.py`, `repositories.py`, `paths.py`: models, validated
  JSON persistence, data locations.
- `macro_player/ui/`: main window, pages, dock, mini player, dialogs, tray.
- `macro_player/app.py`: entry point, single instance; `gui_qt.py` calls it.
- `packaging/`: PyInstaller build script and Inno Setup installer.
- `legacy/gui.py`: the old Tkinter interface, kept for reference only.

The visual and interaction contract is documented in `docs/UI_DESIGN.md`.

## License

The application source code is released under the [MIT License](LICENSE).
The music sheets in `sheets/` are community transcriptions and are **not**
covered by that license; the underlying songs may be protected by copyright
held by their original authors. Use them for personal, non-commercial play.

Automating keyboard input may be restricted by a game's terms of service.
Use the app responsibly and at your own risk.
