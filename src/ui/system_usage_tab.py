"""
System Usage: live graphics-memory and RAM gauges (via src.system_monitor's PDH-based
per-process GPU reader), the active speech/language engines, and how much disk space
Wisperno Pro takes (src.storage_usage). Monitoring only - configuration lives in Settings.
"""

import os

from PySide6.QtCore import QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src import storage_usage
from src.config import get_app_data_dir, get_base_dir
from src.system_monitor import SystemMonitor
from src.ui import theme
from src.ui.scroll_utils import make_scrollable_layout

# Segment colours of the storage bar (also the legend dots).
_STORAGE_PARTS = (
    ("app", "Application files", theme.STORAGE_APP),
    ("models", "AI models", theme.STORAGE_MODELS),
    ("history", "History database", theme.STORAGE_HISTORY),
    ("recordings", "Saved recordings", theme.STORAGE_RECORDINGS),
)


class _Gauge(QWidget):
    """A 270-degree ring with the percentage in the middle. Turns red above 85%."""

    def __init__(self, color_a: str, color_b: str, size: int = 124):
        super().__init__()
        self._a, self._b = QColor(color_a), QColor(color_b)
        self._fraction = 0.0
        self._text = "--"
        self.setFixedSize(size, size)

    def set_value(self, fraction: float, text: str) -> None:
        self._fraction = max(0.0, min(1.0, fraction))
        self._text = text
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        width = 11
        rect = QRectF(width, width, w - 2 * width, h - 2 * width)
        start, span = 225 * 16, -270 * 16
        track = QPen(QColor(theme.BORDER_SUBTLE), width)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(track)
        p.drawArc(rect, start, span)
        if self._fraction > 0:
            if self._fraction > 0.85:
                pen = QPen(QColor(theme.DANGER), width)
            else:
                grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
                grad.setColorAt(0, self._a)
                grad.setColorAt(1, self._b)
                pen = QPen(grad, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, start, int(span * self._fraction))
        p.setPen(QColor(theme.TEXT_PRIMARY))
        font = QFont("Inter Tight")
        font.setPixelSize(int(h * 0.22))
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


class _SegmentBar(QWidget):
    """A single rounded bar split into proportional coloured segments."""

    def __init__(self):
        super().__init__()
        self._segments = []  # (fraction, QColor)
        self.setFixedHeight(14)

    def set_segments(self, parts) -> None:
        total = sum(v for v, _ in parts) or 1
        self._segments = [(v / total, QColor(c)) for v, c in parts if v > 0]
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        clip = QPainterPath()
        clip.addRoundedRect(rect, 7, 7)
        p.fillPath(clip, QColor(theme.BORDER_SUBTLE))
        p.setClipPath(clip)
        x = 0.0
        for fraction, color in self._segments:
            seg_w = rect.width() * fraction
            p.fillRect(QRectF(x, 0, max(seg_w - 2, 1), rect.height()), color)  # 2px gap between segments
            x += seg_w
        p.end()


class _StorageScan(QThread):
    """Walks the install folder off the GUI thread - an 8 GB install has tens of thousands of files."""

    done = Signal(dict)

    def run(self) -> None:
        self.done.emit(storage_usage.storage_breakdown())


def _card() -> tuple:
    frame = QFrame(objectName="usageCard")
    frame.setStyleSheet(
        f"#usageCard {{ background-color: {theme.BG_CARD}; border: 1px solid {theme.BORDER_SUBTLE}; border-radius: 14px; }}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 20)
    layout.setSpacing(12)
    return frame, layout


def _caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 9pt; font-weight: 600; letter-spacing: 1px; background: transparent;")
    return label


def _muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 9pt; background: transparent;")
    return label


def _big(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-family: {theme.FONT_FAMILY_DISPLAY}; font-size: 15pt; font-weight: 600; background: transparent;")
    return label


class SystemUsageTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.monitor = SystemMonitor()
        self._scan = None

        layout = make_scrollable_layout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)
        title = QLabel("System Usage")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        layout.addWidget(_muted("What Wisperno Pro is using right now, and how much space it takes on this PC."))

        # Shown while a preset switch (or the app's own first startup) reloads Whisper/the LLM.
        self.reload_banner = QLabel("Loading the AI engine (Whisper + language model) - this can take a few seconds...")
        self.reload_banner.setWordWrap(True)
        self.reload_banner.setStyleSheet(
            f"background-color: {theme.BG_CARD}; color: {theme.ACCENT_PRIMARY}; border: 1px solid {theme.BORDER_SUBTLE}; "
            f"border-radius: 10px; padding: 10px 14px; font-weight: 600;"
        )
        self.reload_banner.setVisible(False)
        layout.addWidget(self.reload_banner)
        if hasattr(engine, "state_changed"):
            engine.state_changed.connect(self._on_engine_state_changed)

        # ---- Graphics memory + RAM gauges ----
        gauges = QHBoxLayout()
        gauges.setSpacing(16)

        vram_card, vl = _card()
        row = QHBoxLayout()
        row.setSpacing(20)
        self.vram_gauge = _Gauge(*theme.GAUGE_VRAM)
        row.addWidget(self.vram_gauge)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(_caption("GRAPHICS MEMORY"))
        self.vram_main = _big("Reading...")
        col.addWidget(self.vram_main)
        self.vram_label = _muted("")
        col.addWidget(self.vram_label)
        self.vram_sub_label = _muted("")
        col.addWidget(self.vram_sub_label)
        col.addStretch()
        row.addLayout(col, 1)
        vl.addLayout(row)
        gauges.addWidget(vram_card, 1)

        ram_card, rl = _card()
        row = QHBoxLayout()
        row.setSpacing(20)
        self.ram_gauge = _Gauge(*theme.GAUGE_RAM)
        row.addWidget(self.ram_gauge)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(_caption("MEMORY (RAM)"))
        self.ram_main = _big("Reading...")
        col.addWidget(self.ram_main)
        self.ram_label = _muted("")
        col.addWidget(self.ram_label)
        self.ram_sub_label = _muted("")
        col.addWidget(self.ram_sub_label)
        col.addStretch()
        row.addLayout(col, 1)
        rl.addLayout(row)
        gauges.addWidget(ram_card, 1)
        layout.addLayout(gauges)

        # ---- Active engines ----
        engine_card, el = _card()
        el.addWidget(_caption("ACTIVE ENGINES"))
        self.stt_label = _muted("...")
        self.llm_label = _muted("...")
        self.perf_label = _muted("...")
        for lbl in (self.stt_label, self.llm_label, self.perf_label):
            lbl.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
            el.addWidget(lbl)
        layout.addWidget(engine_card)

        # ---- Disk space ----
        disk_card, dl = _card()
        head = QHBoxLayout()
        head.addWidget(_caption("DISK SPACE"))
        head.addStretch()
        self.open_folder_btn = QPushButton("Open install folder")
        self.open_folder_btn.clicked.connect(self._open_install_folder)
        head.addWidget(self.open_folder_btn)
        dl.addLayout(head)
        self.disk_total = _big("Calculating...")
        dl.addWidget(self.disk_total)
        self.disk_sub = _muted("")
        dl.addWidget(self.disk_sub)
        self.disk_bar = _SegmentBar()
        dl.addWidget(self.disk_bar)
        self._legend_sizes = {}
        for key, label, color in _STORAGE_PARTS:
            line = QHBoxLayout()
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
            line.addWidget(dot)
            name = QLabel(label)
            name.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent;")
            line.addWidget(name)
            line.addStretch()
            size = QLabel("")
            size.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-family: {theme.FONT_FAMILY_MONO}; background: transparent;")
            line.addWidget(size)
            dl.addLayout(line)
            self._legend_sizes[key] = size
        layout.addWidget(disk_card)

        layout.addStretch()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(2000)
        self.refresh()
        self.refresh_storage()

    def reset_scroll(self) -> None:
        self._scroll_area.verticalScrollBar().setValue(0)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_storage()  # sizes change as history grows / recordings rotate

    def _on_engine_state_changed(self, state: str) -> None:
        self.reload_banner.setVisible(state == "loading")

    # ---- live meters ----
    def refresh(self) -> None:
        snap = self.monitor.snapshot()
        gpu_total_gb = snap["gpu_total_mb"] / 1024
        app_vram_gb = snap["app_vram_mb"] / 1024
        gpu_used_gb = snap["gpu_used_mb"] / 1024
        ram_total_gb = snap["ram_total_mb"] / 1024
        ram_used_gb = snap["ram_used_mb"] / 1024
        app_ram_gb = snap["app_ram_mb"] / 1024
        ram_free_gb = max(ram_total_gb - ram_used_gb, 0.0)

        if gpu_total_gb > 0:
            pct = gpu_used_gb / gpu_total_gb
            self.vram_gauge.set_value(pct, f"{pct * 100:.0f}%")
            self.vram_main.setText(f"{gpu_used_gb:.1f} of {gpu_total_gb:.1f} GB")
            wisperno_txt = f"Wisperno Pro uses {app_vram_gb:.1f} GB"
            if snap["app_vram_source"] != "per-process counter":
                wisperno_txt += " (estimated)"
            if snap["app_shared_mb"] >= 100:
                wisperno_txt += f", plus {snap['app_shared_mb'] / 1024:.1f} GB spilled into system RAM"
            self.vram_label.setText(wisperno_txt)
            util_txt = f"{snap['gpu_util_pct']}%" if snap["gpu_util_pct"] is not None else "n/a"
            temp_txt = f"{snap['gpu_temp_c']}°C" if snap["gpu_temp_c"] is not None else "n/a"
            self.vram_sub_label.setText(f"Graphics load {util_txt}  -  {temp_txt}")
        else:
            self.vram_gauge.set_value(0, "--")
            self.vram_main.setText("No NVIDIA GPU found")
            self.vram_label.setText("Running in CPU compatibility mode.")
            self.vram_sub_label.setText("")

        pct = ram_used_gb / ram_total_gb if ram_total_gb > 0 else 0.0
        self.ram_gauge.set_value(pct, f"{pct * 100:.0f}%")
        self.ram_main.setText(f"{ram_used_gb:.1f} of {ram_total_gb:.1f} GB")
        self.ram_label.setText(f"Wisperno Pro uses {app_ram_gb:.1f} GB  -  {ram_free_gb:.1f} GB free on this PC")
        self.ram_sub_label.setText(f"Processor load {snap['cpu_util_pct']:.0f}%  -  {snap['thread_count']} threads")

        self._refresh_engine_card()

    def _refresh_engine_card(self) -> None:
        transcriber = self.engine.transcriber
        transformer = self.engine.transformer

        if transcriber is not None:
            cfg = transcriber.config
            self.stt_label.setText(f"Speech recognition:  Whisper {cfg.model_name} ({cfg.compute_type})")
        else:
            self.stt_label.setText("Speech recognition:  not loaded yet")

        if transformer is not None and transformer.llm is not None:
            total = transformer.active_model_layers
            offload = transformer.config.n_gpu_layers
            if offload < 0:
                pct_txt = "all on the graphics card"  # llama.cpp's own "all layers" convention
            elif total:
                pct_txt = "all on the graphics card" if offload >= total else f"{offload} of {total} layers on the graphics card"
            else:
                pct_txt = f"{offload} layers on the graphics card"
            self.llm_label.setText(f"Language model:  {transformer.active_model_name} ({pct_txt})")
        else:
            self.llm_label.setText("Language model:  not loaded yet")

        rows = self.engine.db.list_history(limit=10)
        if rows:
            last_latency_s = rows[0]["latency_ms"] / 1000.0
            self.perf_label.setText(f"Last dictation took {last_latency_s:.2f} s from end of speech to typed text")
        else:
            self.perf_label.setText("No dictation yet this session.")

    # ---- disk space ----
    def refresh_storage(self) -> None:
        if self._scan is not None and self._scan.isRunning():
            return
        self._scan = _StorageScan(self)
        self._scan.done.connect(self._apply_storage)
        self._scan.start()

    def _apply_storage(self, info: dict) -> None:
        total = storage_usage.total_bytes(info)
        self.disk_total.setText(f"{storage_usage.format_bytes(total)} used by Wisperno Pro")
        free = info.get("free")
        self.disk_sub.setText(
            (f"{storage_usage.format_bytes(free)} still free on this drive." if free is not None else "")
            + ("" if info.get("app") is not None else "  (Running from source, so application files aren't counted.)")
        )
        self.disk_bar.set_segments([(int(info.get(k) or 0), c) for k, _, c in _STORAGE_PARTS])
        for key, _, _ in _STORAGE_PARTS:
            value = info.get(key)
            self._legend_sizes[key].setText("-" if value is None else storage_usage.format_bytes(value))

    def _open_install_folder(self) -> None:
        folder = get_base_dir()
        if hasattr(os, "startfile"):
            os.startfile(folder)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        if self._scan is not None:
            self._scan.wait(2000)
        super().closeEvent(event)
