"""Settings page. Widgets only emit intents; the window validates and saves."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..engine import MacroPlayer
from ..i18n import LANGUAGES, tr


def _section(title: str, help_text: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 18, 0, 0)
    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    if help_text:
        label = QLabel(help_text)
        label.setObjectName("muted")
        label.setWordWrap(True)
        layout.addWidget(label)
    return frame, layout


class SettingsPage(QWidget):
    reduced_motion_changed = Signal(bool)
    layout_changed = Signal(str)
    custom_layout_saved = Signal(str)
    countdown_changed = Signal(int)
    queue_gap_changed = Signal(int)
    minimize_to_tray_changed = Signal(bool)
    preview_sound_changed = Signal(bool)
    test_window_requested = Signal()
    pick_target_requested = Signal()
    reset_target_requested = Signal()
    diagnostics_requested = Signal()
    onboarding_requested = Signal()
    open_data_requested = Signal()
    check_updates_changed = Signal(bool)
    language_changed = Signal(str)
    check_now_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        self.content_layout = layout
        scroll.setWidget(content)
        outer.addWidget(scroll)
        eyebrow = QLabel(tr("TÙY CHỌN"))
        eyebrow.setObjectName("eyebrow")
        title = QLabel(tr("Cài đặt"))
        title.setObjectName("pageTitle")
        layout.addWidget(eyebrow)
        layout.addWidget(title)

        frame, section = _section(tr("Phát nhạc"))
        form = QFormLayout()
        self.key_layout = QComboBox()
        self.key_layout.setAccessibleName(tr("Bộ phím trong game"))
        for key, detail in MacroPlayer.KEY_LAYOUTS.items():
            self.key_layout.addItem(tr(detail["name"]), key)
        self.key_layout.addItem(tr("Bộ tùy chỉnh"), "custom")
        self.custom_keys = QLineEdit()
        self.custom_keys.setMaxLength(15)
        self.custom_keys.setPlaceholderText(tr("15 phím, hàng 1 → hàng 3"))
        self.custom_keys.setToolTip(tr("Ví dụ bộ cũ: yuiophjkl;nm,./"))
        self.custom_keys.setAccessibleName(tr("15 phím của bộ tùy chỉnh"))
        self.custom_apply = QPushButton(tr("Lưu bộ phím"))
        self.custom_apply.setProperty("outline", True)
        custom_row = QHBoxLayout()
        custom_row.addWidget(self.custom_keys, 1)
        custom_row.addWidget(self.custom_apply)
        self.countdown = QSlider(Qt.Orientation.Horizontal)
        self.countdown.setRange(0, 30)
        self.countdown.setValue(3)
        self.countdown.setAccessibleName(tr("Thời gian đếm ngược"))
        self.countdown_value = QLabel(tr("3 giây"))
        self.countdown_value.setMinimumWidth(56)
        countdown_row = QHBoxLayout()
        countdown_row.addWidget(self.countdown, 1)
        countdown_row.addWidget(self.countdown_value)
        form.addRow(tr("Bộ phím trong game"), self.key_layout)
        form.addRow(tr("Phím tùy chỉnh"), custom_row)
        form.addRow(tr("Đếm ngược"), countdown_row)
        self.queue_gap = QSpinBox()
        self.queue_gap.setRange(0, 10)
        self.queue_gap.setValue(1)
        self.queue_gap.setSuffix(tr(" giây"))
        self.queue_gap.setAccessibleName(tr("Nghỉ giữa các bài trong hàng chờ"))
        self.queue_gap.setToolTip(tr(
            "Khi hàng chờ tự chuyển bài hoặc lặp bài, chỉ nghỉ ngần này thay vì đếm ngược. "
            "Bài đầu tiên vẫn đếm ngược để bạn kịp vào game."))
        form.addRow(tr("Nghỉ giữa các bài"), self.queue_gap)
        section.addLayout(form)
        layout.addWidget(frame)

        frame, section = _section(tr("Giao diện"))
        self.language = QComboBox()
        self.language.setAccessibleName(tr("Ngôn ngữ giao diện"))
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.language_note = QLabel(tr("Áp dụng sau khi mở lại ứng dụng."))
        self.language_note.setObjectName("muted")
        language_row = QHBoxLayout()
        language_row.addWidget(self.language)
        language_row.addWidget(self.language_note, 1)
        language_form = QFormLayout()
        language_form.addRow(tr("Ngôn ngữ"), language_row)
        section.addLayout(language_form)
        self.reduced_motion = QCheckBox(tr("Giảm chuyển động của Note Runway"))
        self.always_on_top = QCheckBox(tr("Giữ mini player trên cùng"))
        self.always_on_top.setChecked(True)
        self.minimize_to_tray = QCheckBox(tr("Đóng cửa sổ thì thu xuống khay hệ thống"))
        self.preview_sound = QCheckBox(tr("Phát âm thanh khi dùng chế độ Xem trước"))
        self.preview_sound.setChecked(True)
        widget: QWidget
        for widget in (self.reduced_motion, self.always_on_top,
                       self.minimize_to_tray, self.preview_sound):
            section.addWidget(widget)
        layout.addWidget(frame)

        frame, section = _section(
            tr("Giữ phím trong game"),
            tr("Khi game mất focus, bản nhạc tự tạm dừng để không gõ nhầm vào ứng dụng khác. "
            "Mặc định nhận cửa sổ Sky (Sky.exe); có thể chọn game khác như Heartopia."))
        self.focus_lock_checkbox = QCheckBox(tr("Bật chế độ khóa vào cửa sổ game"))
        self.resume_focus_checkbox = QCheckBox(tr("Tự tiếp tục khi quay lại game"))
        self.target_label = QLabel(tr("Mục tiêu: Sky (Sky.exe)"))
        self.target_label.setObjectName("muted")
        buttons = QGridLayout()
        self.detect_button = QPushButton(tr("Kiểm tra cửa sổ"))
        self.pick_button = QPushButton(tr("Chọn cửa sổ game khác…"))
        self.reset_target_button = QPushButton(tr("Dùng lại Sky"))
        for index, button in enumerate((self.detect_button, self.pick_button,
                                        self.reset_target_button)):
            button.setProperty("outline", True)
            buttons.addWidget(button, index // 2, index % 2)
        for widget in (self.focus_lock_checkbox, self.resume_focus_checkbox, self.target_label):
            section.addWidget(widget)
        section.addLayout(buttons)
        layout.addWidget(frame)

        frame, section = _section(tr("Hỗ trợ"))
        self.check_updates = QCheckBox(tr("Tự kiểm tra bản mới trên GitHub khi mở ứng dụng"))
        section.addWidget(self.check_updates)
        support = QGridLayout()
        self.onboarding_button = QPushButton(tr("Mở hướng dẫn thiết lập"))
        self.diagnostics_button = QPushButton(tr("Xuất báo cáo chẩn đoán…"))
        self.open_data_button = QPushButton(tr("Mở thư mục dữ liệu"))
        self.check_now_button = QPushButton(tr("Kiểm tra cập nhật"))
        for index, button in enumerate((self.onboarding_button, self.diagnostics_button,
                                        self.open_data_button, self.check_now_button)):
            button.setProperty("outline", True)
            support.addWidget(button, index // 2, index % 2)
        section.addLayout(support)
        self.version_label = QLabel()
        self.version_label.setObjectName("muted")
        self.version_label.setWordWrap(True)
        self.version_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        section.addWidget(self.version_label)
        layout.addWidget(frame)
        layout.addStretch(1)

        self.reduced_motion.toggled.connect(self.reduced_motion_changed)
        self.key_layout.currentIndexChanged.connect(
            lambda _: self.layout_changed.emit(self.key_layout.currentData()))
        self.custom_apply.clicked.connect(
            lambda: self.custom_layout_saved.emit(self.custom_keys.text()))
        self.countdown.valueChanged.connect(self._countdown)
        self.queue_gap.valueChanged.connect(self.queue_gap_changed)
        self.minimize_to_tray.toggled.connect(self.minimize_to_tray_changed)
        self.preview_sound.toggled.connect(self.preview_sound_changed)
        self.detect_button.clicked.connect(self.test_window_requested)
        self.pick_button.clicked.connect(self.pick_target_requested)
        self.reset_target_button.clicked.connect(self.reset_target_requested)
        self.diagnostics_button.clicked.connect(self.diagnostics_requested)
        self.onboarding_button.clicked.connect(self.onboarding_requested)
        self.open_data_button.clicked.connect(self.open_data_requested)
        self.check_updates.toggled.connect(self.check_updates_changed)
        self.language.currentIndexChanged.connect(
            lambda _: self.language_changed.emit(self.language.currentData()))
        self.check_now_button.clicked.connect(self.check_now_requested)

    def _countdown(self, value: int) -> None:
        self.countdown_value.setText(tr("{value} giây").format(value=value))
        self.countdown_changed.emit(value)

    def set_target(self, exe_name: str | None) -> None:
        self.target_label.setText(
            tr("Mục tiêu: {exe_name} (do bạn chọn)").format(
                exe_name=exe_name) if exe_name else tr("Mục tiêu: Sky (Sky.exe)"))
        self.reset_target_button.setVisible(bool(exe_name))
