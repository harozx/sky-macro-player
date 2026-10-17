import uuid

from PySide6.QtWidgets import QWidget

import macro_player.app as app_module
from macro_player.app import acquire_instance_lock


def test_single_instance_lock_rejects_second_process(tmp_path):
    path = tmp_path / "app.lock"
    first = acquire_instance_lock(path)
    assert first is not None
    try:
        assert acquire_instance_lock(path) is None
    finally:
        first.unlock()

    replacement = acquire_instance_lock(path)
    assert replacement is not None
    replacement.unlock()


def test_second_instance_requests_existing_window_activation(qtbot, monkeypatch):
    server_name = f"sky-instrument-test-{uuid.uuid4()}"
    monkeypatch.setattr(app_module, "INSTANCE_SERVER", server_name)

    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.activations = 0
        def showNormal(self):
            self.activations += 1
            super().showNormal()

    window = Window()
    qtbot.addWidget(window)
    server = app_module.install_instance_server(window)
    try:
        assert app_module.request_existing_instance()
        qtbot.waitUntil(lambda: window.activations == 1, timeout=1000)
    finally:
        server.close()
