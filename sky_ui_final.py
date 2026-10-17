"""Final interaction layer: editable hotkeys, safe shutdown, lasting statuses."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

import sky_ui_integrated as integration
from macro_player.domain import Settings
from macro_player.repositories import RepositoryError
from macro_player.window_focus import FocusService, WindowInfo, WindowsFocusService
from sky_ui_core import SHEETS_DIR, Song, Tokens
from sky_ui_integrated import canonical_hotkey
from sky_ui_polish import MainWindow as PolishedWindow


class DefaultHotkeyService(integration.GlobalHotkeyService):
    """Keeps the legacy F10 stop / F11 next defaults."""

    def start(self, settings: Settings) -> bool:
        hotkeys = dict(settings.hotkeys)
        hotkeys.setdefault("stop", "f10")
        hotkeys.setdefault("next", "f11")
        return super().start(replace(settings, hotkeys=hotkeys))


class DisabledHotkeyService(integration.GlobalHotkeyService):
    """Test/headless service that never installs an operating-system hook."""

    def start(self, settings: Settings) -> bool:
        return True

    def stop(self) -> None:
        self._listener = None


class EditableHotkeysPage(QWidget):
    save_requested = Signal(object)

    RESERVED = integration.GlobalHotkeyService.RESERVED

    def __init__(self, settings: Settings, songs: list[Song]) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        title = QLabel("Phím tắt")
        title.setObjectName("pageTitle")
        copy = QLabel("Thay đổi global hotkeys và bài được gán, sau đó lưu để áp dụng.")
        copy.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(copy)
        layout.addSpacing(14)
        form = QFormLayout()
        self.action_fields = {
            "pause": QLineEdit(settings.pause_hotkey),
            "stop": QLineEdit(settings.hotkeys.get("stop", "F10")),
            "next": QLineEdit(settings.hotkeys.get("next", "F11")),
        }
        form.addRow("Tạm dừng / tiếp tục", self.action_fields["pause"])
        form.addRow("Dừng", self.action_fields["stop"])
        form.addRow("Bài tiếp theo", self.action_fields["next"])
        self.slot_fields: list[tuple[QLineEdit, QComboBox]] = []
        references: list[tuple[Song, str]] = []
        for item in songs:
            try:
                reference = item.path.resolve().relative_to(SHEETS_DIR.resolve()).as_posix()
            except ValueError:
                reference = item.path.as_posix()
            references.append((item, reference))
        for index, key in enumerate(settings.hotkey_keys):
            shortcut = QLineEdit(key)
            song = QComboBox()
            song.addItem("Chưa gán", None)
            for item, reference in references:
                song.addItem(item.title, reference)
            selected = settings.song_slots[index] if index < len(settings.song_slots) else None
            if selected:
                normalized = selected.replace(chr(92), "/")
                match = song.findData(normalized)
                if match < 0:
                    legacy_matches = [
                        row for row, (_, reference) in enumerate(references, start=1)
                        if __import__("pathlib").Path(reference).name.casefold()
                        == __import__("pathlib").Path(normalized).name.casefold()
                    ]
                    if len(legacy_matches) == 1:
                        match = legacy_matches[0]
                song.setCurrentIndex(max(0, match))
            row = QHBoxLayout()
            row.addWidget(shortcut, 1)
            row.addWidget(song, 3)
            form.addRow(f"Ô bài {index + 1}", row)
            self.slot_fields.append((shortcut, song))
        layout.addLayout(form)
        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        save = QPushButton("Lưu và áp dụng")
        save.setProperty("primary", True)
        save.setMinimumHeight(40)
        save.clicked.connect(self._save)
        layout.addWidget(self.feedback)
        layout.addWidget(save)
        layout.addStretch(1)

    def values(self) -> dict:
        return {
            "pause": self.action_fields["pause"].text().strip(),
            "stop": self.action_fields["stop"].text().strip(),
            "next": self.action_fields["next"].text().strip(),
            "slot_keys": tuple(field.text().strip() for field, _ in self.slot_fields),
            "song_slots": tuple(combo.currentData() for _, combo in self.slot_fields),
        }

    def validate_values(self) -> tuple[bool, str]:
        values = self.values()
        raw = [values["pause"], values["stop"], values["next"], *values["slot_keys"]]
        if any(not key for key in raw):
            return False, "Mỗi hành động và ô bài cần một phím tắt."
        canonical = [canonical_hotkey(key) for key in raw]
        if len(canonical) != len(set(canonical)):
            return False, "Một phím đang được dùng cho nhiều hành động."
        if any(key in self.RESERVED for key in canonical):
            return False, "Một phím được Windows giữ riêng. Hãy chọn tổ hợp khác."
        return True, ""

    def show_feedback(self, message: str, success: bool) -> None:
        self.feedback.setStyleSheet(
            f"color: {Tokens.SKY_BLUE if success else Tokens.DANGER};"
        )
        self.feedback.setText(message)

    def _save(self) -> None:
        valid, message = self.validate_values()
        if not valid:
            self.show_feedback(message, False)
            return
        self.save_requested.emit(self.values())


class MainWindow(PolishedWindow):
    def __init__(self, *, enable_global_hotkeys: bool = True,
                 hotkey_service: integration.GlobalHotkeyService | None = None,
                 focus_service: FocusService | None = None) -> None:
        service = hotkey_service
        if service is None:
            service = DefaultHotkeyService() if enable_global_hotkeys else DisabledHotkeyService()
        super().__init__(hotkey_service=service)
        self.close_pending = False
        self.focus_service = focus_service or WindowsFocusService()
        self.sky_window: WindowInfo | None = None
        self.active_sky_window: WindowInfo | None = None
        self.focus_paused = False
        self._install_hotkey_editor()
        self._install_focus_lock_controls()
        try:
            self.hotkeys.pause_requested.disconnect(self.controller.toggle_pause)
        except RuntimeError:
            pass
        self.hotkeys.pause_requested.connect(self.toggle_play)
        self.focus_timer = QTimer(self)
        self.focus_timer.setInterval(250)
        self.focus_timer.timeout.connect(self._poll_focus_lock)
        self.focus_timer.start()

    def _install_focus_lock_controls(self) -> None:
        panel = QWidget()
        panel.setObjectName("focusLockPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 16, 0, 0)
        title = QLabel("Giữ phím trong Sky")
        title.setStyleSheet("font-weight: 600;")
        help_text = QLabel(
            "Khi Sky mất focus, bản nhạc tự tạm dừng để không gõ nhầm vào ứng dụng khác."
        )
        help_text.setObjectName("muted")
        help_text.setWordWrap(True)
        self.focus_lock_checkbox = QCheckBox("Bật chế độ khóa vào cửa sổ Sky")
        self.focus_lock_checkbox.setChecked(self.settings.focus_lock_enabled)
        self.resume_focus_checkbox = QCheckBox("Tự tiếp tục khi quay lại Sky")
        self.resume_focus_checkbox.setChecked(self.settings.resume_on_sky_focus)
        detect = QPushButton("Kiểm tra cửa sổ Sky")
        detect.setMinimumHeight(36)
        detect.clicked.connect(self._test_sky_window)
        for widget in (title, help_text, self.focus_lock_checkbox,
                       self.resume_focus_checkbox, detect):
            layout.addWidget(widget)
        page_layout = getattr(
            self.settings_page, "content_layout", self.settings_page.layout()
        )
        page_layout.insertWidget(max(0, page_layout.count() - 1), panel)
        self.focus_lock_checkbox.toggled.connect(self._set_focus_lock)
        self.resume_focus_checkbox.toggled.connect(self._set_resume_on_focus)

    def _set_focus_lock(self, enabled: bool) -> None:
        if self.controller.busy:
            blocker = QSignalBlocker(self.focus_lock_checkbox)
            self.focus_lock_checkbox.setChecked(self.settings.focus_lock_enabled)
            del blocker
            self.dock.status.setStyleSheet(f"color: {Tokens.APRICOT};")
            self.dock.status.setText(
                "Hãy dừng bài trước khi đổi chế độ khóa vào Sky."
            )
            return
        if not self._save_settings(focus_lock_enabled=enabled):
            blocker = QSignalBlocker(self.focus_lock_checkbox)
            self.focus_lock_checkbox.setChecked(self.settings.focus_lock_enabled)
            del blocker
            return
        if not enabled:
            self._set_playback_guard(None)
            self.active_sky_window = None
        if not enabled and self.focus_paused:
            self.controller.resume_for_focus()
            self.focus_paused = False

    def _set_resume_on_focus(self, enabled: bool) -> None:
        if not self._save_settings(resume_on_sky_focus=enabled):
            blocker = QSignalBlocker(self.resume_focus_checkbox)
            self.resume_focus_checkbox.setChecked(self.settings.resume_on_sky_focus)
            del blocker

    def _locate_sky_window(self) -> WindowInfo | None:
        if self.sky_window is not None and self._valid_sky_target(self.sky_window):
            return self.sky_window
        self.sky_window = self.focus_service.find_sky_window()
        return self.sky_window

    def _valid_sky_target(self, window: WindowInfo) -> bool:
        validator = getattr(self.focus_service, "validate_target", None)
        if callable(validator):
            return bool(validator(window))
        return bool(self.focus_service.is_window(window))

    def _set_playback_guard(self, guard) -> None:
        setter = getattr(self.controller, "set_input_guard", None)
        if callable(setter):
            setter(guard)

    def _guard_for_target(self, window: WindowInfo):
        def target_is_foreground() -> bool:
            if not self.settings.focus_lock_enabled:
                return True
            return (
                self._valid_sky_target(window)
                and self.focus_service.is_foreground(window)
            )
        return target_is_foreground

    def _test_sky_window(self) -> None:
        window = self._locate_sky_window()
        if window is None:
            self._show_error("Không tìm thấy cửa sổ Sky. Hãy mở game rồi thử lại.")
            return
        self.dock.status.setStyleSheet(f"color: {Tokens.SKY_BLUE};")
        self.dock.status.setText(f"Đã tìm thấy Sky: {window.title}")

    @Slot(object)
    def play_song(self, song: Song) -> bool:
        if self._closing:
            return False
        if self.settings.focus_lock_enabled and not self.controller.busy:
            window = self._locate_sky_window()
            if window is None:
                self._show_error("Không tìm thấy cửa sổ Sky. Hãy mở game rồi nhấn Phát lại.")
                return False
            if not self.focus_service.activate(window):
                self._show_error(
                    "Windows chưa cho phép chuyển focus sang Sky. Hãy click vào Sky rồi nhấn Phát."
                )
                return False
            self.active_sky_window = window
            self._set_playback_guard(self._guard_for_target(window))
        elif not self.controller.busy:
            self.active_sky_window = None
            self._set_playback_guard(None)
        return super().play_song(song)

    def toggle_play(self) -> None:
        if self._closing:
            return
        if self.controller.state == "focus_paused":
            window = self.active_sky_window
            if (window is None or not self._valid_sky_target(window)
                    or not self.focus_service.activate(window)):
                self._show_error("Hãy mở và chọn cửa sổ Sky trước khi tiếp tục.")
                return
            self.controller.resume_for_focus()
            self.focus_paused = False
            return
        super().toggle_play()

    def _poll_focus_lock(self) -> None:
        if not self.settings.focus_lock_enabled or not self.controller.busy:
            return
        window = self.active_sky_window or self._locate_sky_window()
        focused = window is not None and self.focus_service.is_foreground(window)
        if not focused and not self.focus_paused:
            if self.controller.pause_for_focus():
                self.focus_paused = True
                self.dock.status.setStyleSheet(f"color: {Tokens.APRICOT};")
                self.dock.status.setText("Sky mất focus · bản nhạc đã tạm dừng")
        elif focused and self.focus_paused and self.settings.resume_on_sky_focus:
            if self.controller.resume_for_focus():
                self.focus_paused = False
                self.dock.status.setStyleSheet("")
                self.dock.status.setText("Đã quay lại Sky · đang tiếp tục")

    @Slot(str)
    def _state_changed(self, state: str) -> None:
        super()._state_changed(state)
        if state == "focus_paused":
            self.dock.runway.set_playing(False)
            self.dock.status.setStyleSheet(f"color: {Tokens.APRICOT};")
            self.dock.status.setText("Sky mất focus · bản nhạc đã tạm dừng")
            self.dock.play_button.setText("Trở lại Sky")
            self.mini.play_button.setText("Trở lại Sky")

    def _install_hotkey_editor(self) -> None:
        old = self.hotkeys_page
        editor = EditableHotkeysPage(self.settings, self.songs)
        editor.save_requested.connect(self._save_hotkeys)
        self.pages.removeWidget(old)
        self.pages.insertWidget(1, editor)
        self.hotkeys_page = editor
        old.deleteLater()

    @Slot(object)
    def _save_hotkeys(self, values: Mapping) -> None:
        previous = self.settings
        hotkeys = dict(self.settings.hotkeys)
        hotkeys.update(stop=values["stop"], next=values["next"])
        updated = replace(
            self.settings,
            pause_hotkey=values["pause"],
            hotkeys=hotkeys,
            hotkey_keys=values["slot_keys"],
            song_slots=values["song_slots"],
        )
        if not self.hotkeys.start(updated):
            self.hotkeys_page.show_feedback(
                "Không thể áp dụng; cấu hình và phím tắt đang dùng được giữ nguyên.",
                False,
            )
            return
        try:
            if self.settings_error:
                self.settings_repository.recover(updated)
                self.settings_error = None
            else:
                self.settings_repository.save(updated)
        except RepositoryError as exc:
            restored = self.hotkeys.start(previous)
            recovery = (
                "Đã khôi phục phím tắt cũ."
                if restored
                else "Không thể khôi phục listener cũ; hãy mở lại ứng dụng."
            )
            self.hotkeys_page.show_feedback(
                f"Không thể lưu cấu hình: {exc}. {recovery}", False
            )
            return
        self.settings = updated
        self.hotkeys_page.show_feedback("Đã lưu và áp dụng global hotkeys.", True)

    @Slot(bool)
    def _playback_finished(self, completed: bool) -> None:
        self.focus_paused = False
        self.active_sky_window = None
        self._set_playback_guard(None)
        super()._playback_finished(completed)
        if not self._closing and self.controller.state != "error" and not self.pending_song:
            self.dock.status.setStyleSheet("")
            self.dock.status.setText("Đã phát xong" if completed else "Đã dừng")
        if self.close_pending:
            self.close_pending = False
            QTimer.singleShot(0, self.close)

    def closeEvent(self, event) -> None:
        self._closing = True
        self.pending_song = None
        self.focus_timer.stop()
        self.hotkeys.stop()
        if self.controller.busy:
            self.close_pending = True
            self.stop_playback()
            self.dock.status.setText("Đang dừng an toàn trước khi đóng")
            event.ignore()
            return
        self.mini.close()
        event.accept()
