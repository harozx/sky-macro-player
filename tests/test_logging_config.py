import logging
import sys
import threading
from pathlib import Path

from macro_player.logging_config import LOGGER_NAME, configure_logging


def _flush(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        handler.flush()


def test_configure_logging_is_idempotent_and_redacts_keys(tmp_path: Path) -> None:
    logger = configure_logging(data_dir=tmp_path)
    same_logger = configure_logging(data_dir=tmp_path)
    managed = [handler for handler in logger.handlers if hasattr(handler, "baseFilename")]
    assert same_logger is logger
    assert len(managed) == 1

    logger.info("pressed_key=f8 action=play")
    _flush(logger)
    text = (tmp_path / "logs" / "application.log").read_text(encoding="utf-8")
    assert "f8" not in text
    assert "key=[REDACTED]" in text


def test_rotating_log_keeps_bounded_backups(tmp_path: Path) -> None:
    logger = configure_logging(data_dir=tmp_path, max_bytes=180, backup_count=2)
    for index in range(30):
        logger.info("rotation-event-%s %s", index, "x" * 80)
    _flush(logger)
    files = list((tmp_path / "logs").glob("application.log*"))
    assert (tmp_path / "logs" / "application.log") in files
    assert len(files) == 3


def test_sys_exception_hook_writes_traceback(tmp_path: Path) -> None:
    logger = configure_logging(data_dir=tmp_path)
    try:
        raise RuntimeError("hook-test")
    except RuntimeError:
        exc_type, exc_value, traceback = sys.exc_info()
        sys.excepthook(exc_type, exc_value, traceback)
    _flush(logger)
    text = (tmp_path / "logs" / "application.log").read_text(encoding="utf-8")
    assert "Unhandled exception in main thread" in text
    assert "RuntimeError: hook-test" in text


def test_thread_exception_hook_writes_traceback(tmp_path: Path) -> None:
    logger = configure_logging(data_dir=tmp_path)

    def fail() -> None:
        raise RuntimeError("thread-hook-test")

    worker = threading.Thread(target=fail, name="test-worker")
    worker.start()
    worker.join()
    _flush(logger)
    text = (tmp_path / "logs" / "application.log").read_text(encoding="utf-8")
    assert "Unhandled exception in worker thread" in text
    assert "RuntimeError: thread-hook-test" in text
    assert logging.getLogger(LOGGER_NAME) is logger
