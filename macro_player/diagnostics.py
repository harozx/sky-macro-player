"""User-initiated diagnostic report. Never includes typed keys or hotkey values."""

from __future__ import annotations

import json
import platform
import sys
import time
import zipfile
from pathlib import Path
from typing import Iterable

from . import __version__
from .domain import Settings


def redacted_settings(settings: Settings) -> dict:
    data = settings.to_dict()
    data["hotkeys"] = {action: "<redacted>" for action in data.get("hotkeys", {})}
    data["hotkey_keys"] = ["<redacted>"] * len(data.get("hotkey_keys", []))
    data["pause_hotkey"] = "<redacted>"
    data["custom_layout_keys"] = ["<redacted>"] * len(data.get("custom_layout_keys", []))
    return data


def build_report(destination: Path, *, settings: Settings, library_summary: dict,
                 log_dir: Path | None, extra: dict | None = None,
                 max_log_bytes: int = 512_000) -> Path:
    destination = Path(destination)
    info = {
        "app_version": __version__,
        "python": sys.version,
        "platform": platform.platform(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **(extra or {}),
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("info.json", json.dumps(info, ensure_ascii=False, indent=2))
        archive.writestr("settings.json",
                         json.dumps(redacted_settings(settings), ensure_ascii=False, indent=2))
        archive.writestr("library.json", json.dumps(library_summary, ensure_ascii=False, indent=2))
        for path in _log_files(log_dir):
            data = path.read_bytes()[-max_log_bytes:]
            archive.writestr(f"logs/{path.name}", data)
    return destination


def _log_files(log_dir: Path | None) -> Iterable[Path]:
    if log_dir is None or not Path(log_dir).is_dir():
        return ()
    return sorted(path for path in Path(log_dir).iterdir()
                  if path.is_file() and ".log" in path.name)
