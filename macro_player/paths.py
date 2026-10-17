"""One source of truth for bundled resources and per-user data locations.

* Bundled sheets ship next to the code (source checkout), inside the
  PyInstaller bundle, or under ``share/`` for a wheel install.
* User data always lives in ``%LOCALAPPDATA%\\SkyMacroPlayer`` so that runtime
  files never mix with the source tree. ``SKY_MACRO_DATA_DIR`` overrides it for
  tests and portable builds.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from .i18n import tr

APP_NAME = "SkyMacroPlayer"
DATA_DIR_ENV = "SKY_MACRO_DATA_DIR"

if getattr(sys, "frozen", False):
    APP_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    APP_DIR = Path(__file__).resolve().parent.parent


def bundled_sheets_dir() -> Path:
    candidates = (
        APP_DIR / "sheets",
        Path(sys.prefix) / "share" / "sky-macro-player" / "sheets",
    )
    return next((path for path in candidates if path.is_dir()), candidates[0])


def user_data_dir() -> Path:
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / APP_NAME


def settings_file() -> Path:
    return user_data_dir() / "hotkeys.json"


def favorites_file() -> Path:
    return user_data_dir() / "favorites.json"


def library_state_file() -> Path:
    return user_data_dir() / "library_state.json"


def user_sheets_dir() -> Path:
    return user_data_dir() / "sheets"


_SEED_MARKER = ".bundled-seeded"


def seed_user_sheets(source: Path | None = None, target: Path | None = None) -> tuple[Path, ...]:
    """Copy bundled sheets into the user library once per file.

    A marker remembers which bundled files were already offered, so a sheet the
    user deleted is not restored, while sheets added by a later release are.
    Existing user files are never overwritten.
    """
    source = source or bundled_sheets_dir()
    target = target or user_sheets_dir()
    if not source.is_dir() or source.resolve() == target.resolve():
        return ()
    target.mkdir(parents=True, exist_ok=True)
    marker = target / _SEED_MARKER
    try:
        seeded = set(json.loads(marker.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        seeded = set()
    copied: list[Path] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".json"}:
            continue
        relative = path.relative_to(source).as_posix()
        if relative in seeded:
            continue
        destination = target / relative
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            copied.append(destination)
        seeded.add(relative)
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(sorted(seeded), ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, marker)
    return tuple(copied)


def migrate_legacy_user_data(
    *, data_dir: Path | None = None,
    legacy_dirs: tuple[Path, ...] | None = None,
) -> tuple[Path, ...]:
    """Copy settings/favorites from older locations once; never overwrite."""
    data_dir = data_dir or user_data_dir()
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    sources = legacy_dirs or (APP_DIR, Path.cwd(), Path(base) / "SkyInstrumentConsole")
    copied: list[Path] = []
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        for name in ("hotkeys.json", "favorites.json"):
            destination = data_dir / name
            if destination.exists():
                continue
            source = next(
                (folder / name for folder in sources
                 if (folder / name).is_file()
                 and (folder / name).resolve() != destination.resolve()),
                None,
            )
            if source is not None:
                shutil.copy2(source, destination)
                copied.append(destination)
    except OSError as exc:
        raise RuntimeError(tr("Không thể chuyển dữ liệu người dùng: {exc}").format(
            exc=exc)) from exc
    return tuple(copied)
