"""Dialogs for text sheets ("sheet chữ") and batch-processing a downloaded folder."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..batch import BatchItem
from ..i18n import N_, tr
from ..text_sheet import TextSheet, parse_text_sheet
from .theme import STYLE, Tokens
from .widgets import KeyGrid, NoteRunway, format_duration

FORMAT_LABELS = (("auto", N_("Tự nhận")), ("number", N_("Số (1 2 3 5 6 1')")),
                 ("solfege", N_("Đô Rê Mi")), ("keys", N_("Chữ phím (y u i o p…)")))
EXAMPLE = ("1 2 3 - 5 6 1' -\n"
           "(1 3 5) - 6 5 | 3 2 1 -")


class TextSheetDialog(QDialog):
    preview_requested = Signal(list, str)
    stop_preview_requested = Signal()
    save_requested = Signal(str, list)

    def __init__(self, key_map: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Nhập sheet chữ"))
        self.setStyleSheet(STYLE)
        self.resize(820, 720)
        self.key_map = dict(key_map)
        self.sheet = TextSheet()
        root = QVBoxLayout(self)
        title = QLabel(tr("Nhập sheet chữ"))
        title.setObjectName("pageTitle")
        help_text = QLabel(tr(
            "Dán sheet dạng số, Đô Rê Mi hoặc chữ phím. Dấu ' lên một quãng tám, dấu , xuống "
            "một quãng tám; (…) hoặc […] là hợp âm; - hoặc _ là nghỉ một nhịp; dấu | được bỏ "
            "qua. Mỗi ký hiệu là một bước nhịp."))
        help_text.setObjectName("muted")
        help_text.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(help_text)

        form = QFormLayout()
        self.format = QComboBox()
        self.format.setAccessibleName(tr("Kiểu sheet chữ"))
        for value, label in FORMAT_LABELS:
            self.format.addItem(tr(label), value)
        self.octave = QComboBox()
        self.octave.setAccessibleName(tr("Quãng tám của nốt 1"))
        self.octave.addItem(tr("Nốt 1 = phím đầu tiên (thấp)"), 0)
        self.octave.addItem(tr("Nốt 1 = phím thứ 8 (giữa)"), 1)
        self.tempo = QSpinBox()
        self.tempo.setRange(30, 400)
        self.tempo.setValue(120)
        self.tempo.setSuffix(" BPM")
        self.per_beat = QComboBox()
        self.per_beat.setAccessibleName(tr("Số ký hiệu mỗi phách"))
        for count in (1, 2, 4):
            self.per_beat.addItem(tr("{count} ký hiệu mỗi phách").format(count=count), count)
        self.line_rest = QSpinBox()
        self.line_rest.setRange(0, 8)
        self.line_rest.setSuffix(tr(" nhịp"))
        self.line_rest.setToolTip(tr("Thêm khoảng nghỉ sau mỗi dòng (thường là cuối câu nhạc)."))
        tempo_row = QHBoxLayout()
        tempo_row.addWidget(self.tempo)
        tempo_row.addWidget(self.per_beat)
        tempo_row.addStretch(1)
        form.addRow(tr("Kiểu"), self.format)
        form.addRow(tr("Quãng tám"), self.octave)
        form.addRow(tr("Nhịp độ"), tempo_row)
        form.addRow(tr("Nghỉ cuối dòng"), self.line_rest)
        root.addLayout(form)

        self.text = QPlainTextEdit()
        self.text.setAccessibleName(tr("Nội dung sheet chữ"))
        self.text.setPlaceholderText(EXAMPLE)
        self.text.setMinimumHeight(140)
        root.addWidget(self.text, 1)

        preview = QFrame()
        preview.setObjectName("detailPanel")
        preview_layout = QVBoxLayout(preview)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.issues = QLabel()
        self.issues.setWordWrap(True)
        self.issues.setStyleSheet(f"color: {Tokens.APRICOT};")
        self.ignore_issues = QCheckBox(tr("Bỏ qua các ký hiệu lỗi khi lưu"))
        self.runway = NoteRunway()
        self.key_grid = KeyGrid()
        self.key_grid.set_labels(list(self.key_map.values()))
        grid_row = QHBoxLayout()
        grid_row.addStretch(1)
        grid_row.addWidget(self.key_grid)
        grid_row.addStretch(1)
        listen_row = QHBoxLayout()
        self.listen_button = QPushButton(tr("Nghe thử"))
        self.listen_button.setProperty("outline", True)
        self.stop_button = QPushButton(tr("Dừng nghe"))
        self.stop_button.setProperty("compact", True)
        listen_row.addWidget(self.listen_button)
        listen_row.addWidget(self.stop_button)
        listen_row.addStretch(1)
        for part in (self.summary, self.issues, self.ignore_issues, self.runway):
            preview_layout.addWidget(part)
        preview_layout.addLayout(grid_row)
        preview_layout.addLayout(listen_row)
        root.addWidget(preview)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel(tr("Tên bài")))
        self.name = QLineEdit(tr("Sheet chữ mới"))
        self.name.setAccessibleName(tr("Tên sheet mới"))
        save_row.addWidget(self.name, 1)
        self.save_button = QPushButton(tr("Lưu thành bài mới"))
        self.save_button.setProperty("primary", True)
        close = QPushButton(tr("Đóng"))
        save_row.addWidget(self.save_button)
        save_row.addWidget(close)
        root.addLayout(save_row)
        self.saved_label = QLabel()
        root.addWidget(self.saved_label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.reparse)
        self.text.textChanged.connect(self._timer.start)
        for signal in (self.format.currentIndexChanged, self.octave.currentIndexChanged,
                       self.tempo.valueChanged, self.per_beat.currentIndexChanged,
                       self.line_rest.valueChanged):
            signal.connect(lambda *_: self._timer.start())
        self.ignore_issues.toggled.connect(lambda *_: self._sync_buttons())
        self.listen_button.clicked.connect(
            lambda: self.preview_requested.emit(list(self.sheet.events), self.name.text().strip()))
        self.stop_button.clicked.connect(self.stop_preview_requested)
        self.save_button.clicked.connect(self._save)
        close.clicked.connect(self.reject)
        self.reparse()

    @property
    def step_ms(self) -> float:
        return 60000 / self.tempo.value() / int(self.per_beat.currentData())

    def reparse(self) -> None:
        self.sheet = parse_text_sheet(
            self.text.toPlainText(), fmt=self.format.currentData(), step_ms=self.step_ms,
            key_map=self.key_map, base_octave=int(self.octave.currentData()),
            line_rest_steps=self.line_rest.value())
        sheet = self.sheet
        detected = dict(FORMAT_LABELS).get(sheet.detected_format, sheet.detected_format)
        duration = int(sheet.events[-1][0]) if sheet.events else 0
        summary = tr("Nhận là: {format} · {notes} nốt · {length}").format(
            format=tr(detected), notes=sheet.note_count, length=format_duration(duration))
        if sheet.folded:
            summary += tr(" · {count} nốt ngoài 15 phím đã gập quãng tám").format(
                count=sheet.folded)
        self.summary.setText(summary if self.text.toPlainText().strip() else
                             tr("Dán sheet chữ vào ô phía trên để xem trước."))
        shown = [issue.describe() for issue in sheet.issues[:5]]
        if len(sheet.issues) > 5:
            shown.append(tr("… và {count} lỗi khác").format(count=len(sheet.issues) - 5))
        self.issues.setText("\n".join(shown))
        self.ignore_issues.setVisible(bool(sheet.issues))
        moments = sorted({int(time) for time, _ in sheet.events})
        self.runway.set_timeline(moments, moments[-1] if moments else 0)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        ready = bool(self.sheet.events) and (
            not self.sheet.issues or self.ignore_issues.isChecked())
        self.save_button.setEnabled(ready)
        self.listen_button.setEnabled(bool(self.sheet.events))

    def flash_keys(self, keys: list) -> None:
        self.key_grid.flash(keys)

    def set_progress(self, elapsed: int) -> None:
        self.runway.set_progress(elapsed)

    def _save(self) -> None:
        name = self.name.text().strip()
        if not name:
            self.show_error(tr("Hãy đặt tên cho bản mới."))
            return
        self.save_requested.emit(name, list(self.sheet.events))

    def show_saved(self, file_name: str) -> None:
        self.saved_label.setStyleSheet(f"color: {Tokens.SUCCESS};")
        self.saved_label.setText(tr("Đã lưu “{name}” vào thư viện. Bạn có thể chỉnh tiếp và lưu "
                                    "thêm bản khác.").format(name=file_name))

    def show_error(self, message: str) -> None:
        self.saved_label.setStyleSheet(f"color: {Tokens.DANGER};")
        self.saved_label.setText(message)


STATUS_LABELS = {"ok": N_("Giữ nguyên"), "changed": N_("Đã xử lý"),
                 "review": N_("Cần nghe lại"), "error": N_("Lỗi")}


class BatchDialog(QDialog):
    """Shows what will happen to every file before anything is written."""

    def __init__(self, items: list[BatchItem],
                 reanalyze: Callable[[bool, bool], list[BatchItem]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Xử lý thư mục sheet"))
        self.setStyleSheet(STYLE)
        self.resize(900, 560)
        self.items = items
        self._reanalyze = reanalyze
        layout = QVBoxLayout(self)
        intro = QLabel(tr(
            "Mỗi bài được kiểm tra; chỉ những chỉnh sửa an toàn mới được làm tự động. File gốc "
            "không bị thay đổi, kết quả được thêm vào thư viện và có thể hoàn tác."))
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)
        options = QHBoxLayout()
        self.merge = QCheckBox(tr("Gộp lớp 2Key/3Key"))
        self.merge.setChecked(True)
        self.fix_timing = QCheckBox(tr("Chỉnh nhịp bài lệch nhẹ"))
        self.fix_timing.setChecked(True)
        self.fix_timing.setToolTip(tr(
            "Chỉ chỉnh khi các nốt nằm quanh một lưới rõ ràng, lệch không quá 15 ms."))
        self.skip_review = QCheckBox(tr("Bỏ qua bài cần nghe lại"))
        for box in (self.merge, self.fix_timing, self.skip_review):
            options.addWidget(box)
        options.addStretch(1)
        layout.addLayout(options)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("File"), tr("Tên bài"), tr("Trạng thái"),
                                              tr("Chi tiết")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        buttons = QDialogButtonBox()
        self.import_button = buttons.addButton("", QDialogButtonBox.ButtonRole.AcceptRole)
        self.import_button.setProperty("primary", True)
        buttons.addButton(tr("Hủy"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.merge.toggled.connect(lambda *_: self._refresh(rerun=True))
        self.fix_timing.toggled.connect(lambda *_: self._refresh(rerun=True))
        self.skip_review.toggled.connect(lambda *_: self._refresh())
        self._refresh()

    def selected_items(self) -> list[BatchItem]:
        return [item for item in self.items if item.importable
                and not (self.skip_review.isChecked() and item.status == "review")]

    def _refresh(self, rerun: bool = False) -> None:
        if rerun:
            self.items = self._reanalyze(self.merge.isChecked(), self.fix_timing.isChecked())
        self.table.setRowCount(len(self.items))
        colors = {"changed": Tokens.SKY_BLUE, "review": Tokens.APRICOT, "error": Tokens.DANGER}
        for row, item in enumerate(self.items):
            cells = (item.source.name, item.title, tr(STATUS_LABELS[item.status]), item.describe())
            for column, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                if column == 2 and item.status in colors:
                    cell.setForeground(QColor(colors[item.status]))
                self.table.setItem(row, column, cell)
        counts = {status: sum(item.status == status for item in self.items)
                  for status in STATUS_LABELS}
        self.summary.setText(tr(
            "{total} file · {changed} đã xử lý · {ok} giữ nguyên · {review} cần nghe lại · "
            "{error} lỗi").format(total=len(self.items), **counts))
        selected = len(self.selected_items())
        self.import_button.setText(tr("Thêm {count} bài vào thư viện").format(count=selected))
        self.import_button.setEnabled(selected > 0)
