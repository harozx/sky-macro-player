"""Small compatibility helpers for Qt bindings used by the test suite."""

from PySide6.QtTest import QSignalSpy


if not hasattr(QSignalSpy, "__len__"):
    QSignalSpy.__len__ = lambda self: self.count()
