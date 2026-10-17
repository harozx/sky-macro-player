"""Test isolation: user data lives in a throwaway folder, never LOCALAPPDATA."""

import os
import shutil
import tempfile
from pathlib import Path

from PySide6.QtTest import QSignalSpy

_DATA_DIR = Path(tempfile.mkdtemp(prefix="sky-macro-test-"))
os.environ["SKY_MACRO_DATA_DIR"] = str(_DATA_DIR)

if not hasattr(QSignalSpy, "__len__"):
    QSignalSpy.__len__ = lambda self: self.count()


def pytest_unconfigure(config):
    shutil.rmtree(_DATA_DIR, ignore_errors=True)
