"""Privacy-conscious application logging and crash capture."""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
import threading
from pathlib import Path
from typing import Final


LOGGER_NAME: Final = "macro_player"
_HANDLER_MARKER: Final = "_macro_player_rotating_handler"
_HOOK_LOCK = threading.Lock()
_ORIGINAL_SYS_EXCEPTHOOK = sys.excepthook
_ORIGINAL_THREAD_EXCEPTHOOK = getattr(threading, "excepthook", None)


class _PrivacyFilter(logging.Filter):
    """Remove likely key bindings/presses from messages before persistence.

    Traceback locals are never captured. This filter is an additional guard for
    messages such as ``pressed_key=f9`` accidentally emitted by callers.
    """

    _KEY_VALUE = re.compile(
        r"(?i)\b(?:pressed[_ -]?key|hotkey|shortcut|key)\b\s*(?:=|:|\bis\b)?\s*"
        r"(?:['\"]?)[^\s,;\]\}]+"
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = "<unformattable log message>"
        record.msg = self._KEY_VALUE.sub("key=[REDACTED]", message)
        record.args = ()
        return True


def _default_data_dir(app_name: str) -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / app_name
    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / app_name
    data_home = os.environ.get("XDG_DATA_HOME")
    return (Path(data_home) if data_home else Path.home() / ".local" / "share") / app_name


def _managed_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [handler for handler in logger.handlers if getattr(handler, _HANDLER_MARKER, False)]


def configure_logging(
    app_name: str = "SkyMacroPlayer",
    *,
    data_dir: str | Path | None = None,
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
    level: int = logging.INFO,
) -> logging.Logger:
    """Configure and return the package logger.

    ``data_dir`` is injectable for portable builds and tests. It represents the
    application's data directory; log files are placed in its ``logs`` child.
    Calling this repeatedly for the same destination never adds duplicate
    handlers. Calling it for a new destination safely replaces the old managed
    handler.
    """
    if not isinstance(app_name, str) or not app_name.strip():
        raise ValueError("app_name must be a non-empty string")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    if isinstance(backup_count, bool) or not isinstance(backup_count, int) or backup_count < 1:
        raise ValueError("backup_count must be a positive integer")

    app_data_dir = Path(data_dir) if data_dir is not None else _default_data_dir(app_name.strip())
    log_dir = app_data_dir.expanduser().resolve() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "application.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    desired_path = os.path.normcase(str(log_path))
    reusable: logging.Handler | None = None
    for handler in _managed_handlers(logger):
        current_path = os.path.normcase(str(getattr(handler, "baseFilename", "")))
        if current_path == desired_path and reusable is None:
            reusable = handler
            handler.setLevel(level)
        else:
            logger.removeHandler(handler)
            handler.close()

    if reusable is None:
        handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        setattr(handler, _HANDLER_MARKER, True)
        handler.setLevel(level)
        handler.addFilter(_PrivacyFilter())
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(threadName)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)

    _install_exception_hooks()
    return logger


def _sys_exception_hook(exc_type: type[BaseException], exc_value: BaseException, traceback: object) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        _ORIGINAL_SYS_EXCEPTHOOK(exc_type, exc_value, traceback)  # type: ignore[arg-type]
        return
    logging.getLogger(f"{LOGGER_NAME}.crash").critical(
        "Unhandled exception in main thread",
        exc_info=(exc_type, exc_value, traceback),
    )


def _thread_exception_hook(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        if _ORIGINAL_THREAD_EXCEPTHOOK is not None:
            _ORIGINAL_THREAD_EXCEPTHOOK(args)
        return
    logging.getLogger(f"{LOGGER_NAME}.crash").critical(
        "Unhandled exception in worker thread '%s'",
        getattr(args.thread, "name", "unknown"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def _install_exception_hooks() -> None:
    with _HOOK_LOCK:
        sys.excepthook = _sys_exception_hook
        if hasattr(threading, "excepthook"):
            threading.excepthook = _thread_exception_hook
