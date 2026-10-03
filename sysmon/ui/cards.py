from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from .. import format as fmt
from ..snapshot import Snapshot
from ..theme import THEME
from .widgets import Bar, Card, Chip, ElideText, FitScroll, FlatBody, RoundedPanel, Text


class MemoryCard(Card):
    def __init__(self, snapshot: Snapshot, parent: QWidget | None = None) -> None:
        super().__init__("Memory", "▦", THEME.accent_cyan, parent)
        self._snap = snapshot
        self._ram_value = Text("…", THEME.text, THEME.font_size_md, bold=True, parent=self)
        self.extras.addWidget(self._ram_value)
        self._bar = Bar(self)
        self._bar.set_fill(THEME.accent_blue)
        self.body.addWidget(self._bar)
        stats = QGridLayout()
        stats.setHorizontalSpacing(12)
        stats.setVerticalSpacing(4)
        self._cache = _Stat("Cache")
        self._avail = _Stat("Available")
        self._buffers = _Stat("Buffers")
        self._pressure = _Stat("Pressure")
        stats.addWidget(self._cache, 0, 0)
        stats.addWidget(self._avail, 0, 1)
        stats.addWidget(self._buffers, 1, 0)
        stats.addWidget(self._pressure, 1, 1)
        self.body.addLayout(stats)
        self.body.addStretch(1)

    def refresh(self) -> None:
        mem = self._snap.mem
        self._ram_value.setText(
            f"{fmt.fmt_kb(mem.used_kb)} / {fmt.fmt_kb(mem.total_kb)}" if mem.ready else "…"
        )
        self._bar.set_value(mem.used_pct)
        self._cache.set_value(fmt.fmt_kb(mem.cache_kb) if mem.ready else "…")
        self._avail.set_value(fmt.fmt_kb(mem.available_kb) if mem.ready else "…")
        self._buffers.set_value(fmt.fmt_kb(mem.buffers_kb) if mem.ready else "…")
        if mem.pressure_pct >= 0:
            color = THEME.accent_green if mem.pressure_pct < 20 else THEME.accent_amber if mem.pressure_pct < 50 else THEME.accent_red
            self._pressure.set_value(fmt.fmt_pct(mem.pressure_pct), color)
        else:
            self._pressure.set_value("n/a")


class SwapAttributionCard(Card):
    """Real disk swap only. zram devices are never listed here."""

    def __init__(self, snapshot: Snapshot, parent: QWidget | None = None) -> None:
        super().__init__("Disk swap", "⇄", THEME.accent_amber, parent)
        self._snap = snapshot
        self._areas = QVBoxLayout()
        self._areas.setSpacing(8)
        self.body.addLayout(self._areas)
        self._verdict = Text("Measuring disk swap…", THEME.text_muted, THEME.font_size_md, bold=True, parent=self)
        self._verdict.setWordWrap(True)
        self.body.addWidget(self._verdict)
        self.body.addStretch(1)
        self._area_widgets: list[_SwapArea] = []

    def refresh(self) -> None:
        swap = self._snap.swap
        areas = [area for area in swap.areas if not area.get("isZram")]
        if swap.disk_size_kb <= 0:
            areas = [{"name": "None", "priority": None, "usedKB": 0, "sizeKB": 0, "isZram": False}]
        while len(self._area_widgets) < len(areas):
            widget = _SwapArea(self)
            self._areas.addWidget(widget)
            self._area_widgets.append(widget)
        for index, widget in enumerate(self._area_widgets):
            if index < len(areas):
                widget.set_area(areas[index])
                widget.show()
            else:
                widget.hide()
        if swap.disk_size_kb <= 0:
            text, color = "No disk swap", THEME.text_muted
        elif not swap.has_sample:
            text, color = "Measuring disk swap…", THEME.accent_amber
        elif swap.disk_swap_out_kbps > 0:
            text, color = f"Disk write {fmt.fmt_rate_kbps(swap.disk_swap_out_kbps)}", THEME.accent_red
        elif swap.disk_swap_in_kbps > 0:
            text, color = f"Reading back {fmt.fmt_rate_kbps(swap.disk_swap_in_kbps)}", THEME.accent_amber
        else:
            text, color = "Idle · 0 MB/s", THEME.accent_green
        self._verdict.setText(text)
        self._verdict.set_color(color)


class ZramCard(Card):
    def __init__(self, snapshot: Snapshot, parent: QWidget | None = None) -> None:
        super().__init__("zram", "▣", THEME.accent_cyan, parent)
        self._snap = snapshot
        self._zswap = Chip("zswap", self)
        self._writeback = Chip("writeback", self)
        self.extras.addWidget(self._zswap)
        self.extras.addWidget(self._writeback)
        self._missing = Text("no zram configured", THEME.text_faint, THEME.font_size_sm, parent=self)
        self._missing.setWordWrap(True)
        self.body.addWidget(self._missing)
        stats = QGridLayout()
        stats.setHorizontalSpacing(12)
        stats.setVerticalSpacing(4)
        self._orig = _StatCol("orig")
        self._compr = _StatCol("compr")
        self._mem = _StatCol("mem used")
        self._ratio = _StatCol("ratio")
        stats.addWidget(self._orig, 0, 0)
        stats.addWidget(self._compr, 0, 1)
        stats.addWidget(self._mem, 1, 0)
        stats.addWidget(self._ratio, 1, 1)
        self._stats = QWidget(self)
        self._stats.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._stats.setLayout(stats)
        self.body.addWidget(self._stats)
        self._rate = Text("", THEME.accent_cyan, THEME.font_size_sm, parent=self)
        self._rate.setWordWrap(True)
        self.body.addWidget(self._rate)
        warn = QHBoxLayout()
        self._warn_icon = Text("⚠", THEME.accent_amber, THEME.font_size_sm, parent=self)
        self._warn = Text("", THEME.text_muted, THEME.font_size_sm, parent=self)
        warn.addWidget(self._warn_icon)
        warn.addWidget(self._warn, 1)
        self._warn_row = QWidget(self)
        self._warn_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._warn_row.setLayout(warn)
        self.body.addWidget(self._warn_row)

    def refresh(self) -> None:
        zram = self._snap.zram
        self.set_title(zram.device if zram.exists else "zram")
        self._zswap.set_value(zram.zswap_status, THEME.accent_green if zram.zswap_status == "Off" else THEME.accent_amber)
        self._writeback.set_value(
            zram.writeback_status,
            THEME.accent_green if zram.writeback_status == "none" else THEME.accent_amber,
        )
        self._missing.setVisible(not zram.exists)
        self._stats.setVisible(zram.exists)
        self._rate.setVisible(zram.exists)
        if zram.exists:
            self._orig.set_value(fmt.fmt_bytes(zram.orig_bytes) if zram.ready else "…")
            self._compr.set_value(fmt.fmt_bytes(zram.compr_bytes) if zram.ready else "…")
            self._mem.set_value(fmt.fmt_bytes(zram.mem_used_bytes) if zram.ready else "…")
            ratio_color = THEME.accent_green if zram.ratio >= 2.5 else THEME.accent_amber
            self._ratio.set_value(f"{zram.ratio:.1f}x" if zram.ratio > 0 else "…", ratio_color)
            swap = self._snap.swap
            if swap.has_sample:
                self._rate.setText(f"Compaction {fmt.fmt_rate_kbps(swap.zram_swap_out_kbps)}")
            else:
                self._rate.setText("Measuring compaction…")
        else:
            self._rate.setText("")
        huge = zram.exists and zram.orig_bytes > 0 and zram.huge_pages * 4096 > 0.1 * zram.orig_bytes
        self._warn_row.setVisible(huge)
        if huge:
            self._warn.setText(f"huge pages: {int(zram.huge_pages):,} (compression degrading)")


class VramCard(Card):
    def __init__(self, snapshot: Snapshot, parent: QWidget | None = None) -> None:
        super().__init__("NVIDIA VRAM", "◉", THEME.accent_green, parent, min_height=200)
        self._snap = snapshot
        self._header = Text("n/a", THEME.text, THEME.font_size_md, bold=True, parent=self)
        self._pct = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        self.extras.addWidget(self._header)
        self.extras.addWidget(self._pct)
        self._scroll = FitScroll(self)
        inner = FlatBody()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 4, 0)
        inner_layout.setSpacing(6)
        self._note = Text("querying nvidia-smi…", THEME.text_faint, THEME.font_size_sm, parent=inner)
        self._note.setWordWrap(True)
        inner_layout.addWidget(self._note)
        self._gpus = QVBoxLayout()
        self._gpus.setSpacing(8)
        inner_layout.addLayout(self._gpus)
        self._gpu_widgets: list[_GpuRow] = []
        self._top_label = Text("Top process by VRAM", THEME.text_muted, THEME.font_size_sm, parent=inner)
        inner_layout.addWidget(self._top_label)
        self._procs = QVBoxLayout()
        inner_layout.addLayout(self._procs)
        self._proc_widgets: list[_ProcRow] = []
        self._empty = Text("no VRAM consumers reported", THEME.text_faint, THEME.font_size_sm, parent=inner)
        self._empty.setWordWrap(True)
        inner_layout.addWidget(self._empty)
        inner_layout.addStretch(1)
        self._scroll.setWidget(inner)
        self.body.addWidget(self._scroll, 1)

    def refresh(self) -> None:
        vram = self._snap.vram
        if vram.available:
            self._header.setText(f"{fmt.fmt_kb(vram.gpu_used_mib * 1024)} / {fmt.fmt_kb(vram.gpu_total_mib * 1024)}")
            self._pct.setText(f"  ({fmt.fmt_pct(vram.used_pct)})")
            self._note.hide()
        else:
            self._header.setText("n/a")
            self._pct.setText("")
            self._note.setText("nvidia-smi unavailable — VRAM card disabled" if vram.nvidia_failed else "querying nvidia-smi…")
            self._note.show()
        while len(self._gpu_widgets) < len(vram.gpus):
            widget = _GpuRow(self)
            self._gpus.addWidget(widget)
            self._gpu_widgets.append(widget)
        for index, widget in enumerate(self._gpu_widgets):
            if vram.available and index < len(vram.gpus):
                widget.set_gpu(vram.gpus[index])
                widget.show()
            else:
                widget.hide()
        self._top_label.setVisible(vram.available)
        self._empty.setVisible(vram.available and not vram.procs)
        while len(self._proc_widgets) < len(vram.procs):
            widget = _ProcRow(self)
            self._procs.addWidget(widget)
            self._proc_widgets.append(widget)
        max_mib = vram.procs[0]["mib"] if vram.procs else 1
        for index, widget in enumerate(self._proc_widgets):
            if vram.available and index < len(vram.procs):
                widget.set_proc(vram.procs[index], max_mib, vram.gpu_total_mib)
                widget.show()
            else:
                widget.hide()


class _Stat(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(Text(label, THEME.text_muted, THEME.font_size_sm, parent=self))
        self._value = ElideText("…", THEME.text, THEME.font_size_sm, bold=True, parent=self)
        layout.addWidget(self._value, 1)

    def set_value(self, value: str, color: str = THEME.text) -> None:
        self._value.setText(value)
        self._value.set_color(color)


class _StatCol(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(Text(label, THEME.text_muted, THEME.font_size_sm, parent=self))
        self._value = ElideText("…", THEME.text, THEME.font_size_md + 1, bold=True, parent=self)
        layout.addWidget(self._value)

    def set_value(self, value: str, color: str = THEME.text) -> None:
        self._value.setText(value)
        self._value.set_color(color)


class _SwapArea(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        row = QHBoxLayout()
        self._name = ElideText("", THEME.text, THEME.font_size_md, parent=self)
        self._prio = ElideText("", THEME.text_faint, THEME.font_size_sm, parent=self)
        self._used = ElideText("", THEME.text, THEME.font_size_sm, bold=True, parent=self)
        self._pct = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        row.addWidget(self._name)
        row.addWidget(self._prio)
        row.addStretch(1)
        row.addWidget(self._used)
        row.addWidget(self._pct)
        layout.addLayout(row)
        self._bar = Bar(self)
        layout.addWidget(self._bar)

    def set_area(self, area: dict) -> None:
        self._name.setText(str(area.get("name") or ""))
        used = float(area.get("usedKB") or 0)
        size = float(area.get("sizeKB") or 0)
        priority = area.get("priority")
        if priority is None:
            self._prio.setText("")
        else:
            self._prio.setText(f"priority {int(priority)}")
        self._used.setText(f"{fmt.fmt_kb(used)} / {fmt.fmt_kb(size)}")
        pct = round(100 * used / size) if size > 0 else 0
        self._pct.setText(f"({pct}%)" if size > 0 else "(0%)")
        self._bar.set_value(pct)
        self._bar.set_fill(THEME.accent_amber)


class _GpuRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        row = QHBoxLayout()
        self._index = Text("", THEME.text, THEME.font_size_md, parent=self)
        self._name = ElideText("", THEME.text_faint, THEME.font_size_sm, parent=self)
        self._temp = Text("", THEME.text_muted, THEME.font_size_sm, bold=True, parent=self)
        self._used = Text("", THEME.text, THEME.font_size_sm, bold=True, parent=self)
        self._pct = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        row.addWidget(self._index)
        row.addWidget(self._name)
        row.addWidget(self._temp)
        row.addStretch(1)
        row.addWidget(self._used)
        row.addWidget(self._pct)
        layout.addLayout(row)
        self._bar = Bar(self)
        self._bar.set_fill(THEME.accent_amber)
        layout.addWidget(self._bar)

    def set_gpu(self, gpu: dict) -> None:
        self._index.setText(f"GPU {int(gpu.get('index') or 0)}")
        short = str(gpu.get("shortName") or "")
        self._name.setText(f"•  {short}" if short else "")
        temp = gpu.get("tempC")
        self._temp.setText(fmt.fmt_temp_c(temp) if isinstance(temp, (int, float)) and math.isfinite(temp) and temp > 0 else "")
        used = float(gpu.get("usedMiB") or 0)
        total = float(gpu.get("totalMiB") or 0)
        self._used.setText(f"{fmt.fmt_kb(used * 1024)} / {fmt.fmt_kb(total * 1024)}")
        self._pct.setText(f"({fmt.fmt_pct(float(gpu.get('usedPct') or 0))})")
        self._bar.set_value(float(gpu.get("usedPct") or 0))


class _ProcRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(18)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        dot = RoundedPanel(THEME.accent_amber, THEME.accent_amber, radius=4, border_width=0, parent=self)
        dot.setFixedSize(7, 7)
        self._name = ElideText("", THEME.text, THEME.font_size_sm, parent=self)
        self._bar = Bar(self, height=8)
        self._bar.set_fill(THEME.accent_amber)
        self._used = Text("", THEME.text, THEME.font_size_sm, bold=True, parent=self)
        self._pct = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._name, 2)
        layout.addWidget(self._bar, 3)
        layout.addWidget(self._used)
        layout.addWidget(self._pct)

    def set_proc(self, proc: dict, max_mib: float, gpu_total_mib: float) -> None:
        self._name.setText(str(proc.get("name") or ""))
        mib = float(proc.get("mib") or 0)
        self._bar.set_value(100.0 * mib / max(max_mib, 1.0))
        self._used.setText(fmt.fmt_kb(mib * 1024))
        self._pct.setText(f"{round(100 * mib / gpu_total_mib)}%" if gpu_total_mib > 0 else "")
