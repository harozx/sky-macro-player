"""Sheet editor: merge layers, cut, quantize, transpose, tempo — saved as a new sheet."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..library import Song
from ..sheet_tools import (
    EditOptions, EditReport, Event, apply_edits, detect_grid, grid_candidates, has_layers,
    normalize,
)
from .theme import STYLE, Tokens
from .widgets import KeyGrid, NoteRunway, format_duration


def describe_grid(step_ms: float, ratio: float, base_ms: float | None = None) -> str:
    division = ""
    if base_ms:
        parts = round(base_ms / step_ms)
        division = "1 phách · " if parts == 1 else f"1/{parts} phách · "
    return f"{division}{step_ms:g} ms · {ratio:.0%} khớp"


class SheetEditorDialog(QDialog):
    preview_requested = Signal(list, str)
    stop_preview_requested = Signal()
    save_requested = Signal(str, list)

    def __init__(self, song: Song, events: list[Event], key_labels: list[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Chỉnh sheet — {song.title}")
        self.setStyleSheet(STYLE)
        self.resize(820, 680)
        self.song = song
        self.source = normalize(events)
        self._result: list[Event] = list(self.source)
        self.report = EditReport()
        duration_s = (self.source[-1][0] if self.source else 0) / 1000
        root = QVBoxLayout(self)
        title = QLabel("Chỉnh sheet")
        title.setObjectName("pageTitle")
        grid = detect_grid(self.source)
        source_info = [f"Nguồn: {song.title}",
                       f"{sum(len(keys) for _, keys in self.source)} nốt",
                       format_duration(int(duration_s * 1000))]
        if grid:
            source_info.append(f"lưới {describe_grid(grid.step_ms, grid.on_grid)}")
        info = QLabel(" · ".join(source_info))
        info.setObjectName("muted")
        info.setWordWrap(True)
        note = QLabel("Bản gốc không bao giờ bị sửa. Kết quả được lưu thành một sheet mới "
                      "trong thư viện.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        for widget in (title, info, note):
            root.addWidget(widget)

        form = QFormLayout()
        self.merge = QCheckBox("Gộp lớp 2Key/3Key về 15 phím")
        self.merge.setEnabled(has_layers(self.source))
        self.merge.setChecked(has_layers(self.source))
        if not has_layers(self.source):
            self.merge.setToolTip("Sheet này chỉ có một lớp.")
        form.addRow("Lớp", self.merge)

        self.start = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        for box in (self.start, self.end):
            box.setRange(0, max(0.0, duration_s))
            box.setDecimals(1)
            box.setSingleStep(0.5)
            box.setSuffix(" giây")
        self.end.setValue(duration_s)
        self.whole = QPushButton("Cả bài")
        self.whole.setProperty("compact", True)
        cut_row = QHBoxLayout()
        cut_row.addWidget(QLabel("Từ"))
        cut_row.addWidget(self.start)
        cut_row.addWidget(QLabel("đến"))
        cut_row.addWidget(self.end)
        cut_row.addWidget(self.whole)
        cut_row.addStretch(1)
        form.addRow("Cắt đoạn", cut_row)

        self.quantize = QCheckBox("Chỉnh nhịp theo lưới")
        self.grid_choice = QComboBox()
        self.grid_choice.setAccessibleName("Chọn lưới nhịp")
        candidates = grid_candidates(self.source)
        base = candidates[0].step_ms if candidates else None
        for candidate in candidates:
            self.grid_choice.addItem(describe_grid(candidate.step_ms, candidate.on_grid, base),
                                     candidate.step_ms)
        self.step = QDoubleSpinBox()
        self.step.setRange(10, 5000)
        self.step.setDecimals(1)
        self.step.setSuffix(" ms")
        self.step.setAccessibleName("Bước lưới tùy chỉnh")
        if grid:
            index = self.grid_choice.findData(grid.step_ms)
            self.grid_choice.setCurrentIndex(max(0, index))
            self.step.setValue(grid.step_ms)
        quantize_row = QHBoxLayout()
        quantize_row.addWidget(self.quantize)
        quantize_row.addWidget(self.grid_choice, 1)
        quantize_row.addWidget(self.step)
        form.addRow("Nhịp", quantize_row)
        self.quantize_hint = QLabel()
        self.quantize_hint.setObjectName("muted")
        self.quantize_hint.setWordWrap(True)
        if grid and grid.on_grid >= .98:
            self.quantize_hint.setText(
                "Sheet đã khớp lưới; chỉ cần chỉnh nhịp khi đổi sang lưới thô hơn.")
        else:
            self.quantize_hint.setText(
                "Sheet chưa khớp lưới nào rõ ràng (thường là bản ghi tay). Hãy thử từng lưới "
                "và nghe thử trước khi lưu.")
        form.addRow("", self.quantize_hint)

        self.transpose = QSpinBox()
        self.transpose.setRange(-7, 7)
        self.transpose.setSuffix(" bậc")
        self.transpose.setToolTip("1 bậc = sang phím kế bên; 7 bậc = một quãng tám. "
                                  "Nốt vượt 15 phím được gập quãng tám.")
        form.addRow("Dịch tông", self.transpose)
        self.tempo = QSpinBox()
        self.tempo.setRange(50, 200)
        self.tempo.setValue(100)
        self.tempo.setSingleStep(5)
        self.tempo.setSuffix(" %")
        self.tempo.setToolTip("120% nhanh hơn 20%; thay đổi được lưu vào bản mới.")
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
        self.listen_button = QPushButton("Nghe thử")
        self.listen_button.setProperty("outline", True)
        self.listen_button.setToolTip("Phát bản đã chỉnh trên bàn phím ảo, không gửi phím ra game.")
        self.stop_button = QPushButton("Dừng nghe")
        self.stop_button.setProperty("compact", True)
        listen.addWidget(self.listen_button)
        listen.addWidget(self.stop_button)
        listen.addStretch(1)
        for widget in (self.runway, self.summary, self.warnings):
            preview_layout.addWidget(widget)
        preview_layout.addLayout(grid_row)
        preview_layout.addLayout(listen)
        root.addWidget(preview, 1)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("Tên bản mới"))
        self.name = QLineEdit(f"{song.title} (chỉnh)")
        self.name.setAccessibleName("Tên sheet mới")
        save_row.addWidget(self.name, 1)
        self.save_button = QPushButton("Lưu thành bản mới")
        self.save_button.setProperty("primary", True)
        close = QPushButton("Đóng")
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
        end = self.end.value() * 1000
        whole_end = self.end.value() >= self.end.maximum() - 1e-6
        return EditOptions(
            merge_layers=self.merge.isChecked(),
            start_ms=self.start.value() * 1000,
            end_ms=None if whole_end else end,
            quantize_step_ms=self.step.value() if self.quantize.isChecked() else None,
            transpose_steps=self.transpose.value(),
            tempo_percent=self.tempo.value(),
        )

    def result_events(self) -> list[Event]:
        return list(self._result)

    def recompute(self) -> None:
        if self.start.value() >= self.end.value() and self.end.maximum() > 0:
            self._result, self.report = [], EditReport()
            self.summary.setText("Điểm bắt đầu phải nhỏ hơn điểm kết thúc.")
            self.warnings.setText("")
            self.save_button.setEnabled(False)
            self.listen_button.setEnabled(False)
            return
        self._result, self.report = apply_edits(self.source, self.options())
        report = self.report
        grid_text = (f"{report.grid_before:.0%} → {report.grid_after:.0%}"
                     if report.grid_before is not None and report.grid_after is not None else "—")
        self.summary.setText(
            f"Nốt: {report.notes_before} → {report.notes_after} · "
            f"Thời lượng: {format_duration(int(report.duration_before))} → "
            f"{format_duration(int(report.duration_after))} · Khớp lưới: {grid_text}"
            + (f" · Đã dời {report.moved} nhịp" if report.moved else ""))
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
            self.saved_label.setStyleSheet(f"color: {Tokens.DANGER};")
            self.saved_label.setText("Hãy đặt tên cho bản mới.")
            return
        self.save_requested.emit(name, list(self._result))

    def show_saved(self, file_name: str) -> None:
        self.saved_label.setStyleSheet(f"color: {Tokens.SUCCESS};")
        self.saved_label.setText(f"Đã lưu “{file_name}” vào thư viện. Bạn có thể chỉnh tiếp "
                                 "và lưu thêm bản khác.")

    def show_error(self, message: str) -> None:
        self.saved_label.setStyleSheet(f"color: {Tokens.DANGER};")
        self.saved_label.setText(message)
