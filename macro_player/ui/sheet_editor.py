"""Sheet editor: merge layers, cut, quantize, transpose, tempo — saved as a new sheet."""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import tr
from ..library import Song
from ..sheet_tools import (
    EditOptions,
    EditReport,
    Event,
    apply_edits,
    detect_grid,
    grid_candidates,
    has_layers,
    normalize,
)
from .theme import STYLE, Tokens
from .widgets import KeyGrid, NoteRunway, format_duration


def describe_grid(step_ms: float, ratio: float, base_ms: float | None = None) -> str:
    text = tr("{step} ms · {ratio} khớp").format(step=f"{step_ms:g}", ratio=f"{ratio:.0%}")
    if base_ms:
        parts = round(base_ms / step_ms)
        division = tr("1 phách") if parts == 1 else tr("1/{parts} phách").format(parts=parts)
        text = f"{division} · {text}"
    return text


class SheetEditorDialog(QDialog):
    preview_requested = Signal(list, str)
    stop_preview_requested = Signal()
    save_requested = Signal(str, list)

    def __init__(self, song: Song, events: list[Event], key_labels: list[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Chỉnh sheet — {title}").format(title=song.title))
        self.setStyleSheet(STYLE)
        self.resize(820, 680)
        self.song = song
        self.source = normalize(events)
        self._result: list[Event] = list(self.source)
        self.report = EditReport()
        duration_s = (self.source[-1][0] if self.source else 0) / 1000
        root = QVBoxLayout(self)
        title = QLabel(tr("Chỉnh sheet"))
        title.setObjectName("pageTitle")
        grid = detect_grid(self.source)
        source_info = [
            tr("Nguồn: {title}").format(title=song.title),
            tr("{count} nốt").format(count=sum(len(keys) for _, keys in self.source)),
            format_duration(int(duration_s * 1000)),
        ]
        if grid:
            source_info.append(tr("lưới {grid}").format(
                grid=describe_grid(grid.step_ms, grid.on_grid)))
        info = QLabel(" · ".join(source_info))
        info.setObjectName("muted")
        info.setWordWrap(True)
        note = QLabel(tr("Bản gốc không bao giờ bị sửa. Kết quả được lưu thành một sheet mới "
                         "trong thư viện."))
        note.setObjectName("muted")
        note.setWordWrap(True)
        for widget in (title, info, note):
            root.addWidget(widget)

        form = QFormLayout()
        layered = has_layers(self.source)
        self.merge = QCheckBox(tr("Gộp lớp 2Key/3Key về 15 phím"))
        self.merge.setEnabled(layered)
        self.merge.setChecked(layered)
        if not layered:
            self.merge.setToolTip(tr("Sheet này chỉ có một lớp."))
        form.addRow(tr("Lớp"), self.merge)

        self.start = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        for box in (self.start, self.end):
            box.setRange(0, max(0.0, duration_s))
            box.setDecimals(1)
            box.setSingleStep(0.5)
            box.setSuffix(tr(" giây"))
        self.end.setValue(duration_s)
        self.whole = QPushButton(tr("Cả bài"))
        self.whole.setProperty("compact", True)
        cut_row = QHBoxLayout()
        cut_row.addWidget(QLabel(tr("Từ")))
        cut_row.addWidget(self.start)
        cut_row.addWidget(QLabel(tr("đến")))
        cut_row.addWidget(self.end)
        cut_row.addWidget(self.whole)
        cut_row.addStretch(1)
        form.addRow(tr("Cắt đoạn"), cut_row)

        self.quantize = QCheckBox(tr("Chỉnh nhịp theo lưới"))
        self.grid_choice = QComboBox()
        self.grid_choice.setAccessibleName(tr("Chọn lưới nhịp"))
        candidates = grid_candidates(self.source)
        base = candidates[0].step_ms if candidates else None
        for candidate in candidates:
            self.grid_choice.addItem(describe_grid(candidate.step_ms, candidate.on_grid, base),
                                     candidate.step_ms)
        self.step = QDoubleSpinBox()
        self.step.setRange(10, 5000)
        self.step.setDecimals(1)
        self.step.setSuffix(" ms")
        self.step.setAccessibleName(tr("Bước lưới tùy chỉnh"))
        if grid:
            self.grid_choice.setCurrentIndex(max(0, self.grid_choice.findData(grid.step_ms)))
            self.step.setValue(grid.step_ms)
        quantize_row = QHBoxLayout()
        quantize_row.addWidget(self.quantize)
        quantize_row.addWidget(self.grid_choice, 1)
        quantize_row.addWidget(self.step)
        form.addRow(tr("Nhịp"), quantize_row)
        self.quantize_hint = QLabel()
        self.quantize_hint.setObjectName("muted")
        self.quantize_hint.setWordWrap(True)
        if grid and grid.on_grid >= .98:
            self.quantize_hint.setText(tr(
                "Sheet đã khớp lưới; chỉ cần chỉnh nhịp khi đổi sang lưới thô hơn."))
        else:
            self.quantize_hint.setText(tr(
                "Sheet chưa khớp lưới nào rõ ràng (thường là bản ghi tay). Hãy thử từng lưới "
                "và nghe thử trước khi lưu."))
        form.addRow("", self.quantize_hint)

        self.transpose = QSpinBox()
        self.transpose.setRange(-7, 7)
        self.transpose.setSuffix(tr(" bậc"))
        self.transpose.setToolTip(tr("1 bậc = sang phím kế bên; 7 bậc = một quãng tám. "
                                     "Nốt vượt 15 phím được gập quãng tám."))
        form.addRow(tr("Dịch tông"), self.transpose)
        self.tempo = QSpinBox()
        self.tempo.setRange(50, 200)
        self.tempo.setValue(100)
        self.tempo.setSingleStep(5)
        self.tempo.setSuffix(" %")
        self.tempo.setToolTip(tr("120% nhanh hơn 20%; thay đổi được lưu vào bản mới."))
        form.addRow("Tempo", self.tempo)
        root.addLayout(form)

        preview = QFrame()
        preview.setObjectName("detailPanel")
        preview_layout = QVBoxLayout(preview)
        self.runway = NoteRunway()
        self.key_grid = KeyGrid()
        self.key_grid.set_labels(key_labels)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.warnings = QLabel()
        self.warnings.setWordWrap(True)
        self.warnings.setStyleSheet(f"color: {Tokens.APRICOT};")
        grid_row = QHBoxLayout()
        grid_row.addStretch(1)
        grid_row.addWidget(self.key_grid)
        grid_row.addStretch(1)
        listen = QHBoxLayout()
        self.listen_button = QPushButton(tr("Nghe thử"))
        self.listen_button.setProperty("outline", True)
        self.listen_button.setToolTip(
            tr("Phát bản đã chỉnh trên bàn phím ảo, không gửi phím ra game."))
        self.stop_button = QPushButton(tr("Dừng nghe"))
        self.stop_button.setProperty("compact", True)
        listen.addWidget(self.listen_button)
        listen.addWidget(self.stop_button)
        listen.addStretch(1)
        for part in (self.runway, self.summary, self.warnings):
            preview_layout.addWidget(part)
        preview_layout.addLayout(grid_row)
        preview_layout.addLayout(listen)
        root.addWidget(preview, 1)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel(tr("Tên bản mới")))
        self.name = QLineEdit(tr("{title} (chỉnh)").format(title=song.title))
        self.name.setAccessibleName(tr("Tên sheet mới"))
        save_row.addWidget(self.name, 1)
        self.save_button = QPushButton(tr("Lưu thành bản mới"))
        self.save_button.setProperty("primary", True)
        close = QPushButton(tr("Đóng"))
        save_row.addWidget(self.save_button)
        save_row.addWidget(close)
        root.addLayout(save_row)
        self.saved_label = QLabel()
        self.saved_label.setStyleSheet(f"color: {Tokens.SUCCESS};")
        root.addWidget(self.saved_label)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.recompute)
        for signal in (self.merge.toggled, self.quantize.toggled, self.start.valueChanged,
                       self.end.valueChanged, self.step.valueChanged,
                       self.transpose.valueChanged, self.tempo.valueChanged):
            signal.connect(lambda *_: self._timer.start())
        self.grid_choice.currentIndexChanged.connect(self._grid_chosen)
        self.whole.clicked.connect(self._whole_song)
        self.listen_button.clicked.connect(
            lambda: self.preview_requested.emit(list(self._result), self.name.text().strip()))
        self.stop_button.clicked.connect(self.stop_preview_requested)
        self.save_button.clicked.connect(self._save)
        close.clicked.connect(self.reject)
        self.recompute()

    def _grid_chosen(self, index: int) -> None:
        value = self.grid_choice.itemData(index)
        if value:
            self.step.setValue(float(value))

    def _whole_song(self) -> None:
        self.start.setValue(0)
        self.end.setValue(self.end.maximum())

    def options(self) -> EditOptions:
        whole_end = self.end.value() >= self.end.maximum() - 1e-6
        return EditOptions(
            merge_layers=self.merge.isChecked(),
            start_ms=self.start.value() * 1000,
            end_ms=None if whole_end else self.end.value() * 1000,
            quantize_step_ms=self.step.value() if self.quantize.isChecked() else None,
            transpose_steps=self.transpose.value(),
            tempo_percent=self.tempo.value(),
        )

    def result_events(self) -> list[Event]:
        return list(self._result)

    def recompute(self) -> None:
        if self.start.value() >= self.end.value() and self.end.maximum() > 0:
            self._result, self.report = [], EditReport()
            self.summary.setText(tr("Điểm bắt đầu phải nhỏ hơn điểm kết thúc."))
            self.warnings.setText("")
            self.save_button.setEnabled(False)
            self.listen_button.setEnabled(False)
            return
        self._result, self.report = apply_edits(self.source, self.options())
        report = self.report
        if report.grid_before is not None and report.grid_after is not None:
            grid_text = tr("{before} → {after}").format(
                before=f"{report.grid_before:.0%}", after=f"{report.grid_after:.0%}")
        else:
            grid_text = tr("chưa rõ")
        summary = tr("Nốt: {before} → {after} · Thời lượng: {length_before} → {length_after} "
                     "· Khớp lưới: {grid}").format(
            before=report.notes_before, after=report.notes_after,
            length_before=format_duration(int(report.duration_before)),
            length_after=format_duration(int(report.duration_after)), grid=grid_text)
        if report.moved:
            summary += tr(" · Đã dời {count} nhịp").format(count=report.moved)
        self.summary.setText(summary)
        self.warnings.setText("\n".join(report.warnings))
        moments = sorted({int(time) for time, _ in self._result})
        self.runway.set_timeline(moments, moments[-1] if moments else 0)
        has_notes = bool(self._result)
        self.save_button.setEnabled(has_notes)
        self.listen_button.setEnabled(has_notes)

    def flash_keys(self, keys: list) -> None:
        self.key_grid.flash(keys)

    def set_progress(self, elapsed: int) -> None:
        self.runway.set_progress(elapsed)

    def _save(self) -> None:
        name = self.name.text().strip()
        if not name:
            self.show_error(tr("Hãy đặt tên cho bản mới."))
            return
        self.save_requested.emit(name, list(self._result))

    def show_saved(self, file_name: str) -> None:
        self.saved_label.setStyleSheet(f"color: {Tokens.SUCCESS};")
        self.saved_label.setText(tr("Đã lưu “{name}” vào thư viện. Bạn có thể chỉnh tiếp và lưu "
                                    "thêm bản khác.").format(name=file_name))

    def show_error(self, message: str) -> None:
        self.saved_label.setStyleSheet(f"color: {Tokens.DANGER};")
        self.saved_label.setText(message)
