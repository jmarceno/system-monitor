from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from .. import format as fmt
from ..snapshot import Snapshot
from ..theme import THEME
from .widgets import ElideText, Text


class RingGauge(QWidget):
    def __init__(self, label: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._color = color
        self._temps: list[float] = []
        self._ring_size = 64
        self.setMinimumSize(0, 72)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._ring = QWidget(self)
        self._ring.setFixedSize(self._ring_size, self._ring_size)
        self._ring.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._ring.paintEvent = self._paint_ring  # type: ignore[method-assign]

        self._temp_col = QVBoxLayout()
        self._temp_col.setContentsMargins(0, 0, 0, 0)
        self._temp_col.setSpacing(0)
        self._temp_labels: list[Text] = []
        self._overlay = QWidget(self._ring)
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._overlay.setGeometry(8, 8, self._ring_size - 16, self._ring_size - 16)
        overlay_layout = QVBoxLayout(self._overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.addLayout(self._temp_col)

        text = QVBoxLayout()
        text.setSpacing(0)
        self._label = ElideText(label, THEME.text_muted, THEME.font_size_md, bold=True, parent=self)
        self._pct = Text("0%", THEME.text, 20, bold=True, parent=self)
        self._sub = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        self._detail = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        text.addWidget(self._label)
        text.addWidget(self._pct)
        text.addWidget(self._sub)
        text.addWidget(self._detail)
        layout.addWidget(self._ring, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(text, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        side = int(max(52, min(88, self.height() - 4)))
        if self._ring.width() != side:
            self._ring.setFixedSize(side, side)
            inset = max(6, side // 8)
            self._overlay.setGeometry(inset, inset, side - inset * 2, side - inset * 2)

    def set_reading(
        self,
        value: float,
        sub: str,
        temps: list[float] | None = None,
        temp_c: float | None = None,
        color: str | None = None,
        detail: str = "",
    ) -> None:
        self._value = value if math.isfinite(value) else 0.0
        if color:
            self._color = color
        self._pct.setText(f"{round(self._value)}%" if math.isfinite(value) else "n/a")
        self._sub.setText(sub)
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail))
        source = temps if temps else ([temp_c] if temp_c is not None and math.isfinite(temp_c) and temp_c > 0 else [])
        self._temps = [t for t in source if math.isfinite(t) and t > 0]
        while len(self._temp_labels) < len(self._temps):
            label = Text("", THEME.text_muted, THEME.font_size_sm, bold=True, parent=self)
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self._temp_col.addWidget(label)
            self._temp_labels.append(label)
        for index, label in enumerate(self._temp_labels):
            if index < len(self._temps):
                label.setText(fmt.fmt_temp_c(self._temps[index]))
                label.show()
            else:
                label.hide()
        self._ring.update()

    def _paint_ring(self, _event) -> None:
        painter = QPainter(self._ring)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = self._ring.width()
        height = self._ring.height()
        cx, cy = width / 2, height / 2
        radius = width / 2 - 5
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        start_qt = 135 * 16
        span = int(1.5 * 180 * 16)  # 270°
        pen = QPen(QColor(THEME.track), 6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, start_qt, -span)  # clockwise in Qt is negative span
        frac = max(0.0, min(1.0, self._value / 100.0))
        if frac > 0.001:
            pen.setColor(QColor(self._color))
            painter.setPen(pen)
            painter.drawArc(rect, start_qt, int(-span * frac))


class SummaryGauges:
    """CPU, GPU, RAM and real disk swap. Not a panel — each gauge is its own grid cell."""

    def __init__(self, snapshot: Snapshot, parent: QWidget) -> None:
        self._snap = snapshot
        self.cpu = RingGauge("CPU", THEME.accent_cyan, parent)
        self.gpu = RingGauge("GPU VRAM", THEME.accent_amber, parent)
        self.ram = RingGauge("RAM", THEME.accent_blue, parent)
        self.swap = RingGauge("Swap", THEME.accent_amber, parent)
        self.swap.setToolTip("Real disk swap only. zram is measured in its own section and is not included here.")

    def refresh(self) -> None:
        snap = self._snap
        self.cpu.set_reading(snap.cpu.busy_pct, fmt.fmt_mhz(snap.cpu.mhz), temp_c=snap.cpu.temp_c)
        if snap.vram.available:
            self.gpu.set_reading(
                snap.vram.used_pct,
                fmt.fmt_kb(snap.vram.gpu_used_mib * 1024),
                temps=snap.vram.temps,
                detail=f"/ {fmt.fmt_kb(snap.vram.gpu_total_mib * 1024)}",
            )
        else:
            self.gpu.set_reading(snap.vram.used_pct, "n/a", temps=snap.vram.temps)
        if snap.mem.ready:
            self.ram.set_reading(
                snap.mem.used_pct,
                fmt.fmt_kb(snap.mem.used_kb),
                detail=f"/ {fmt.fmt_kb(snap.mem.total_kb)}",
            )
        else:
            self.ram.set_reading(snap.mem.used_pct, "…")
        # Disk swap only. zram lives in ZramCollector and must not move this gauge.
        swap_color = THEME.accent_red if snap.swap.disk_size_kb > 0 and snap.swap.verdict == 3 else THEME.accent_amber
        self.swap.set_reading(
            snap.swap.used_pct,
            fmt.fmt_kb(snap.swap.disk_used_kb),
            color=swap_color,
            detail=f"/ {fmt.fmt_kb(snap.swap.disk_size_kb)}",
        )
