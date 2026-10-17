"""Build the Windows one-folder app and a portable zip.

Usage: python packaging/build_exe.py [--zip]
Output: dist/SkyMacroPlayer/SkyMacroPlayer.exe (+ dist/SkyMacroPlayer-<version>-portable.zip)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "pyinstaller"
DIST = ROOT / "dist"
NAME = "SkyMacroPlayer"


def version() -> str:
    sys.path.insert(0, str(ROOT))
    from macro_player import __version__
    return __version__


def make_icon(target: Path) -> Path:
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(["build"])
    from macro_player.ui.tray import app_icon
    target.parent.mkdir(parents=True, exist_ok=True)
    pixmap = app_icon().pixmap(256, 256)
    if not pixmap.save(str(target), "ICO"):
        raise SystemExit(f"Could not write icon {target}")
    del app
    return target


def build() -> Path:
    icon = make_icon(BUILD / "app.ico")
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", NAME, "--icon", str(icon),
        "--distpath", str(DIST), "--workpath", str(BUILD), "--specpath", str(BUILD),
        "--add-data", f"{ROOT / 'sheets'};sheets",
        "--add-data", f"{ROOT / 'LICENSE'};.",
        "--collect-submodules", "macro_player",
        "--exclude-module", "tkinter",
        str(ROOT / "packaging" / "launcher.py"),
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    exe = DIST / NAME / f"{NAME}.exe"
    if not exe.is_file():
        raise SystemExit("PyInstaller did not produce the executable")
    return exe


# Not used by a Widgets app: software OpenGL, PDF, QML/Quick runtimes.
PRUNE = ("opengl32sw.dll", "Qt6Pdf.dll", "Qt6Qml.dll", "Qt6QmlModels.dll",
         "Qt6QmlMeta.dll", "Qt6QmlWorkerScript.dll", "Qt6Quick.dll", "Qt6VirtualKeyboard.dll")
KEEP_TRANSLATIONS = ("qtbase_vi", "qtbase_en", "qt_vi", "qt_en")


def prune(app_dir: Path) -> int:
    qt = app_dir / "_internal" / "PySide6"
    removed = 0
    for name in PRUNE:
        target = qt / name
        if target.exists():
            removed += target.stat().st_size
            target.unlink()
    translations = qt / "translations"
    if translations.is_dir():
        for path in translations.glob("*.qm"):
            if not path.stem.startswith(KEEP_TRANSLATIONS):
                removed += path.stat().st_size
                path.unlink()
    return removed


def make_zip(app_dir: Path) -> Path:
    archive = DIST / f"{NAME}-{version()}-portable.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(app_dir.rglob("*")):
            if path.is_file():
                handle.write(path, Path(NAME) / path.relative_to(app_dir))
    return archive


if __name__ == "__main__":
    executable = build()
    print(f"built {executable}; pruned {prune(executable.parent) // 1_000_000} MB")
    if "--zip" in sys.argv:
        print(f"zipped {make_zip(executable.parent)}")
