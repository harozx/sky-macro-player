"""Final language and interaction polish for the integrated console."""

from __future__ import annotations

from PySide6.QtCore import Slot

from sky_ui_core import Song
from sky_ui_integrated import MainWindow as IntegratedWindow


class MainWindow(IntegratedWindow):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.queue.list.model().rowsInserted.connect(self._sync_queue_copy)
        self.queue.list.model().rowsRemoved.connect(self._sync_queue_copy)
        self._sync_queue_copy()
        self._translate_dynamic_controls()
        self._translate_favorite_markers()

    def _translate_dynamic_controls(self) -> None:
        state = self.controller.state
        play_label = "Tiếp tục" if state == "paused" else "Tạm dừng" if state == "playing" else "Phát"
        self.dock.play_button.setText(play_label)
        self.mini.play_button.setText(play_label)
        self.dock.next_button.setText("Tiếp")
        self.dock.stop_button.setText("Dừng")
        self.dock.mini_button.setText("Thu nhỏ")

    def _translate_favorite_markers(self) -> None:
        for index in range(self.library_page.list.count()):
            item = self.library_page.list.item(index)
            item.setText(item.text().replace("FAVORITE", "Yêu thích"))

    @Slot()
    def _sync_queue_copy(self, *args) -> None:
        count = self.queue.list.count()
        self.queue.hint.setText(
            f"{count} bài đang chờ" if count else
            "Hàng chờ đang trống. Chọn một bài trong thư viện và nhấn “Thêm hàng chờ”."
        )

    @Slot(object)
    def _song_changed(self, song: Song) -> None:
        super()._song_changed(song)
        self._translate_dynamic_controls()

    @Slot(str)
    def _state_changed(self, state: str) -> None:
        super()._state_changed(state)
        self._translate_dynamic_controls()

    @Slot(object)
    def toggle_favorite(self, song: Song) -> None:
        super().toggle_favorite(song)
        self._translate_favorite_markers()
