# Changelog

All notable changes to Sky Macro Player. Versions follow
[Semantic Versioning](https://semver.org/); downloads are on the
[Releases](https://github.com/harozx/sky-macro-player/releases) page.

## [3.2.1] - 2026-10-24

### Changed
- Queue: only the first song counts down; later songs follow after a short
  gap (0–10 s, default 1 s) instead of a full countdown.
- The update check and installer point at the renamed
  `harozx/sky-macro-player` repository.

## [3.2.0] - 2026-10-17

### Added
- **Text sheets** (Công cụ → Nhập sheet chữ…): numbers, Do Re Mi and key
  letters, with octave marks, chords, rests and problems reported by line
  and column. Preview, listen and save.
- **Batch processing** (Công cụ → Xử lý cả thư mục sheet…): checks a whole
  downloaded folder, merges layers and snaps hand-played timing only around
  a clear beat grid; uncertain files are marked “Cần nghe lại”. Batch
  imports can be undone.
- Seven public-domain sheets written for the app: *Kìa con bướm vàng*,
  *Twinkle Twinkle Little Star*, *Ode to Joy*, *Jingle Bells*,
  *Minuet in G*, *Mary Had a Little Lamb*, *London Bridge Is Falling Down*.

### Changed
- The queue skips songs that cannot play instead of stopping.

### Removed
- The old Tkinter UI, the `gui_qt.py`/`macro_core.py` shims and superseded
  v2 plans (still in git history). Start the app with
  `python -m macro_player.app`.

## [3.1.0] - 2026-10-17

### Added
- **Hoàn tác nhập**: undo the last sheet import. New copies are removed,
  overwritten files get their previous contents back, and files edited
  afterwards are kept.
- Property-based tests (Hypothesis) for the parser and sheet edits.
- CI fails when coverage of `macro_player` drops below 85 %.

### Fixed
- The packaged build could not import `macro_player`, so v3.0.0 had no
  release files.
- Grid detection crashed when no gap between notes repeated.

## [3.0.0] - 2026-10-17

### Added
- **Sheet editor** (Chỉnh sheet…): merge 2Key/3Key layers, cut a section,
  snap to a detected beat grid, transpose by scale steps and change tempo.
  Saving always creates a new sheet.
- **English UI** option in Settings (applies after a restart).
- Live speed 0.5×–1.5× remembered per song, start from any point on the
  Note Runway, A–B loop.
- Import sheets by dialog or drag-and-drop with validation and
  rename/overwrite/skip; the library refreshes when the folder changes.
- Song details (notes, density, difficulty, play count), Recent filter,
  Most/Recently played sorting, playlists.
- Preview mode on a virtual 15-key grid that never sends keys to the OS.
- Per-song 2Key/3Key policy (merge, layer 1 only, blocked).
- Custom 15-key layout and focus lock on any chosen game window.
- Hotkeys recorded by pressing them; conflicts with music keys rejected.
- System tray, first-run guide, Ctrl+K command palette, diagnostics export.
- Windows installer and portable zip built by CI, opt-in update check
  against GitHub Releases.

### Changed
- One main window built from pages and widgets, one playback controller,
  and user data always in `%LOCALAPPDATA%\SkyMacroPlayer`.
- The window fits 1080p at 200 % scaling.

## [2.1.0] - 2026-10-17

### Added
- Accent-insensitive search (`bang khuang` finds *Bâng khuâng*).
- Sort by name, length or newest; Playable filter; song length.
- Play all, shuffle, repeat off/all/one, clear queue with undo.

## [2.0.0] - 2026-10-17

### Added
- PySide6 “instrument console” UI with library, queue, mini player, Note
  Runway and editable hotkeys.
- Deterministic playback engine: monotonic timing, keys always released,
  input stops as soon as the game loses focus.
- Focus lock pinned to the Sky window.
- Validated data files with atomic writes and backup of corrupt files.
- Test suite and Windows CI for Python 3.10–3.13.
- MIT license for the source code (bundled sheets excluded).

[3.2.1]: https://github.com/harozx/sky-macro-player/compare/v3.2.0...v3.2.1
[3.2.0]: https://github.com/harozx/sky-macro-player/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/harozx/sky-macro-player/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/harozx/sky-macro-player/compare/v2.1.0...v3.0.0
[2.1.0]: https://github.com/harozx/sky-macro-player/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/harozx/sky-macro-player/releases/tag/v2.0.0
