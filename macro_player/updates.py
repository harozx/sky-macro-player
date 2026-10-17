"""Opt-in update check against GitHub Releases. It only informs; it never downloads."""

from __future__ import annotations

import json
import re

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import __version__
from .i18n import tr

RELEASES_API = "https://api.github.com/repos/harozx/macro_project/releases/latest"
RELEASES_PAGE = "https://github.com/harozx/macro_project/releases/latest"


def parse_version(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value.split("-")[0])
    return tuple(int(number) for number in numbers[:3]) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


class UpdateChecker(QObject):
    update_available = Signal(str, str)
    up_to_date = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None

    def check(self) -> None:
        if self._reply is not None:
            return
        request = QNetworkRequest(QUrl(RELEASES_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", f"SkyMacroPlayer/{__version__}".encode())
        request.setTransferTimeout(8000)
        self._reply = self._network.get(request)
        self._reply.finished.connect(self._finished)

    def _finished(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.failed.emit(reply.errorString())
                return
            self.handle_payload(bytes(reply.readAll()))  # type: ignore[call-overload]
        finally:
            reply.deleteLater()

    def handle_payload(self, payload: bytes) -> None:
        try:
            data = json.loads(payload.decode("utf-8"))
            tag = str(data["tag_name"])
            url = str(data.get("html_url") or RELEASES_PAGE)
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            self.failed.emit(tr("Phản hồi từ GitHub không hợp lệ."))
            return
        if not url.startswith("https://github.com/"):
            url = RELEASES_PAGE
        if is_newer(tag):
            self.update_available.emit(tag, url)
        else:
            self.up_to_date.emit()
