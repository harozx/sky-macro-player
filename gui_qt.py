"""Launch the Sky Instrument Console."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths, Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from macro_player.logging_config import configure_logging
from sky_ui_core import migrate_legacy_user_data
from sky_ui_final import MainWindow


INSTANCE_SERVER = "sky-instrument-console-v2"


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


def request_existing_instance(timeout_ms: int = 500) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_SERVER)
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(b"activate")
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


def install_instance_server(window: MainWindow) -> QLocalServer:
    QLocalServer.removeServer(INSTANCE_SERVER)
    server = QLocalServer(window)
    if not server.listen(INSTANCE_SERVER):
        raise RuntimeError(f"Không thể mở kênh instance: {server.errorString()}")

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


def main() -> int:
    logger = configure_logging()
    logger.info("Starting Sky Instrument Console")
    try:
        migrated = migrate_legacy_user_data()
        if migrated:
            logger.info("Migrated %d legacy user data files", len(migrated))
    except RuntimeError as exc:
        logger.error("User data migration failed: %s", exc)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Sky Instrument Console")
    app.setOrganizationName("Sky Instrument")
    app.setStyle("Fusion")
    instance_lock = acquire_instance_lock()
    if instance_lock is None:
        if not request_existing_instance():
            QMessageBox.information(
                None,
                "Sky Instrument Console",
                "Ứng dụng đang chạy nhưng Windows chưa thể đưa cửa sổ đó lên trước.",
            )
        return 0
    window = MainWindow()
    instance_server = install_instance_server(window)
    window._instance_server = instance_server
    window.show()
    try:
        return app.exec()
    finally:
        instance_lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
