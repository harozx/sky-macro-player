"""Application entry point: logging, data migration, single instance, window."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from . import __version__, paths
from .i18n import set_language, tr
from .logging_config import configure_logging

INSTANCE_SERVER = "sky-macro-player-v3"


def acquire_instance_lock(path: str | Path | None = None) -> QLockFile | None:
    """Hold one process-wide lock so global hotkeys cannot be installed twice."""
    if path is None:
        temp_root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.TempLocation
        ) or tempfile.gettempdir()
        path = Path(temp_root) / "sky-macro-player.lock"
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(0)
    return lock if lock.tryLock(100) else None


def request_existing_instance(timeout_ms: int = 500, server_name: str | None = None) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name or INSTANCE_SERVER)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(b"activate")
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


def install_instance_server(window: QWidget, server_name: str | None = None) -> QLocalServer:
    name = server_name or INSTANCE_SERVER
    QLocalServer.removeServer(name)
    server = QLocalServer(window)
    if not server.listen(name):
        raise RuntimeError(tr("Không thể mở kênh instance: {0}").format(server.errorString()))

    def activate() -> None:
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            socket.readAll()
            socket.disconnectFromServer()
            socket.deleteLater()
        window.showNormal()
        window.raise_()
        window.activateWindow()

    server.newConnection.connect(activate)
    return server


def smoke_test(app: QApplication) -> int:
    """Build the real window without hooks or tray, then close it (CI/packaging)."""
    from .hotkeys import DisabledHotkeyService
    from .ui.main_window import MainWindow

    window = MainWindow(hotkey_service=DisabledHotkeyService(), use_tray=False)
    window.show()
    app.processEvents()
    songs = len(window.songs)
    sound = window.synth._load()
    window.close()
    app.processEvents()
    print(f"smoke-test ok: {songs} songs, preview sound {'on' if sound else 'off'}, "
          f"version {__version__}")
    return 0 if songs else 3


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv:
        print(__version__)
        return 0
    logger = configure_logging(data_dir=paths.user_data_dir())
    logger.info("Starting Sky Macro Player")
    try:
        migrated = paths.migrate_legacy_user_data()
        if migrated:
            logger.info("Migrated %d legacy user data files", len(migrated))
    except RuntimeError as exc:
        logger.error("User data migration failed: %s", exc)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv)
    app.setApplicationName("Sky Macro Player")
    app.setOrganizationName("Sky Macro Player")
    app.setStyle("Fusion")
    if "--smoke-test" in argv:
        return smoke_test(app)
    app.setQuitOnLastWindowClosed(False)
    try:
        from .repositories import RepositoryError, SettingsRepository

        set_language(SettingsRepository(paths.settings_file()).load().language)
    except (RepositoryError, OSError):
        pass  # MainWindow reports unreadable settings itself.
    instance_lock = acquire_instance_lock()
    if instance_lock is None:
        if not request_existing_instance():
            QMessageBox.information(
                None, "Sky Macro Player",
                tr("Ứng dụng đang chạy nhưng Windows chưa thể đưa cửa sổ đó lên trước."),
            )
        return 0
    from .ui.main_window import MainWindow

    window = MainWindow(show_onboarding=True)
    window.closed.connect(app.quit)
    window._instance_server = install_instance_server(window)  # type: ignore[attr-defined]
    window.show()
    try:
        return app.exec()
    finally:
        instance_lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
