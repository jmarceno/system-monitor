from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .. import format as fmt
from ..snapshot import Snapshot
from ..theme import THEME
from .widgets import Bar, ElideText, FitScroll, FlatBody, GridCell, Sparkline, Text


class _Column(GridCell):
    """A grid section whose list scrolls inside the cell."""

    def __init__(self, title: str, spacing: int, parent: QWidget | None = None) -> None:
        super().__init__(parent, min_height=140)
        header = QHBoxLayout()
        header.addWidget(ElideText(title, THEME.accent_cyan, THEME.font_size_lg, bold=True, parent=self), 1)
        self._count = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        header.addWidget(self._count)
        self._layout.addLayout(header)
        self._scroll = FitScroll(self)
        self._list = FlatBody()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 4, 0)
        self._list_layout.setSpacing(spacing)
        self._list_layout.addStretch(1)
        self._scroll.setWidget(self._list)
        self._layout.addWidget(self._scroll, 1)
        self._note = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        self._note.setWordWrap(True)
        self._layout.addWidget(self._note)


class StorageSidecar(_Column):
    def __init__(self, snapshot: Snapshot, parent: QWidget | None = None) -> None:
        super().__init__("Storage", 0, parent)
        self._snap = snapshot
        self._rows: list[QWidget] = []

    def refresh(self) -> None:
        storage = self._snap.storage
        self._count.setText(str(len(storage.volumes)) if storage.ready else "")
        if not storage.ready:
            self._scroll.hide()
            self._note.show()
            self._note.setText("Storage query unavailable" if storage.query_failed else "Reading mounted devices…")
            return
        if not storage.rows:
            self._scroll.hide()
            self._note.show()
            self._note.setText("No mounted storage devices")
            return
        self._note.hide()
        self._scroll.show()
        while len(self._rows) < len(storage.rows):
            row = _StorageRow(self._list)
            self._list_layout.insertWidget(self._list_layout.count() - 1, row)
            self._rows.append(row)
        for index, widget in enumerate(self._rows):
            if index < len(storage.rows):
                widget.set_row(storage.rows[index], self._snap.storage_io)
                widget.show()
            else:
                widget.hide()


class AiSpendSidecar(_Column):
    def __init__(self, snapshot: Snapshot, parent: QWidget | None = None) -> None:
        super().__init__("AI spend", 0, parent)
        self._snap = snapshot
        self._cards: list[_SpendCard] = []

    def refresh(self) -> None:
        spend = self._snap.ai_spend
        self._count.setText(str(spend.ok_count) if spend.ready else "")
        if not spend.ready:
            self._scroll.hide()
            self._note.show()
            suffix = f" — {spend.fail_note}" if spend.fail_note else ""
            self._note.setText(
                f"Spend query unavailable{suffix}" if spend.query_failed else "Reading AI spend…"
            )
            return
        self._note.hide()
        self._scroll.show()
        while len(self._cards) < len(spend.providers):
            card = _SpendCard(self._list)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
            self._cards.append(card)
        for index, widget in enumerate(self._cards):
            if index < len(spend.providers):
                widget.set_provider(spend.providers[index])
                widget.show()
            else:
                widget.hide()


class _StorageRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._section = Text("", THEME.text_muted, THEME.font_size_sm, bold=True, parent=self)
        self._body = QWidget(self)
        self._body.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        card_layout = QVBoxLayout(self._body)
        card_layout.setContentsMargins(0, 6, 0, 8)
        card_layout.setSpacing(2)
        name_row = QHBoxLayout()
        self._name = ElideText("", THEME.text, THEME.font_size_md, bold=True, parent=self._body)
        self._kind = Text("", THEME.accent_amber, THEME.font_size_sm, bold=True, parent=self._body)
        name_row.addWidget(self._name, 1)
        name_row.addWidget(self._kind)
        card_layout.addLayout(name_row)
        self._free = ElideText("", THEME.text, THEME.font_size_sm, parent=self._body)
        card_layout.addWidget(self._free)
        self._bar = Bar(self._body, height=6)
        card_layout.addWidget(self._bar)
        self._mount = ElideText("", THEME.text_faint, THEME.font_size_sm, parent=self._body)
        card_layout.addWidget(self._mount)
        io_row = QHBoxLayout()
        io_row.addWidget(Text("I/O", THEME.text, THEME.font_size_sm, bold=True, parent=self._body))
        io_row.addStretch(1)
        self._read = Text("", THEME.text_muted, THEME.font_size_sm, parent=self._body)
        self._write = Text("", THEME.text_muted, THEME.font_size_sm, parent=self._body)
        io_row.addWidget(self._read)
        io_row.addWidget(self._write)
        card_layout.addLayout(io_row)
        self._spark = Sparkline(self._body)
        card_layout.addWidget(self._spark)
        self._rule = QWidget(self)
        self._rule.setFixedHeight(1)
        self._rule.setStyleSheet(f"background: {THEME.window_border};")
        card_layout.addWidget(self._rule)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._section)
        outer.addWidget(self._body)

    def set_row(self, row: dict, storage_io) -> None:
        if row.get("kind") == "section":
            self._section.setText(str(row.get("label") or ""))
            self._section.show()
            self._body.hide()
            return
        self._section.hide()
        self._body.show()
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        volume = row.get("volume") or {}
        self._name.setText(str(volume.get("name") or ""))
        self._kind.setText("USB" if volume.get("isRemovable") else "")
        available = volume.get("availableBytes", -1)
        size = volume.get("sizeBytes", -1)
        if available >= 0 and size > 0:
            self._free.setText(f"{fmt.fmt_bytes(available)} free / {fmt.fmt_bytes(size)}")
        else:
            self._free.setText("free space unavailable")
        used_pct = volume.get("usedPct", 0)
        self._bar.set_value(used_pct if isinstance(used_pct, (int, float)) and used_pct >= 0 else 0)
        self._bar.set_fill(THEME.accent_amber if volume.get("isRemovable") else THEME.accent_blue)
        self._mount.setText(str(volume.get("mountPoint") or ""))
        sample = storage_io.sample_for(volume)
        self._read.setText(f"R  {fmt.fmt_rate_kbps(sample['readKBps'])}")
        self._write.setText(f"W  {fmt.fmt_rate_kbps(sample['writeKBps'])}")
        self._spark.set_history(
            sample.get("history") or [],
            THEME.accent_amber if volume.get("isRemovable") else THEME.accent_cyan,
        )


class _SpendCard(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(3)
        name_row = QHBoxLayout()
        self._name = ElideText("", THEME.text, THEME.font_size_md, bold=True, parent=self)
        self._badge = Text("unoff.", THEME.accent_amber, THEME.font_size_sm, bold=True, parent=self)
        name_row.addWidget(self._name, 1)
        name_row.addWidget(self._badge)
        layout.addLayout(name_row)
        head_row = QHBoxLayout()
        self._headline = Text("n/a", THEME.text_muted, THEME.font_size_lg, bold=True, parent=self)
        self._headline_label = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        head_row.addWidget(self._headline)
        head_row.addWidget(self._headline_label, 1)
        layout.addLayout(head_row)
        self._bar = Bar(self, height=6)
        layout.addWidget(self._bar)
        self._meters = QVBoxLayout()
        layout.addLayout(self._meters)
        self._meter_widgets: list[_Meter] = []
        self._detail = Text("", THEME.text_muted, THEME.font_size_sm, parent=self)
        self._detail.setWordWrap(True)
        layout.addWidget(self._detail)
        self._lines = QVBoxLayout()
        layout.addLayout(self._lines)
        self._line_widgets: list[_Line] = []
        self._note = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        self._note.setWordWrap(True)
        layout.addWidget(self._note)
        rule = QWidget(self)
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {THEME.window_border};")
        layout.addWidget(rule)

    def set_provider(self, provider: dict) -> None:
        self._name.setText(str(provider.get("name") or ""))
        self._badge.setVisible(bool(provider.get("unofficial")))
        self._headline.setText(str(provider.get("headline") or "n/a"))
        pct = provider.get("pct")
        color = _bar_color(pct) if provider.get("status") == "ok" else THEME.text_muted
        self._headline.set_color(color)
        label = provider.get("headlineLabel")
        self._headline_label.setText(str(label) if label else "")
        self._headline_label.setVisible(bool(label))
        meters = provider.get("meters") or []
        show_bar = _has_pct(pct) and not meters
        self._bar.setVisible(show_bar)
        if show_bar:
            self._bar.set_value(float(pct))
            self._bar.set_fill(_bar_color(pct))
        while len(self._meter_widgets) < len(meters):
            meter = _Meter(self)
            self._meters.addWidget(meter)
            self._meter_widgets.append(meter)
        for index, widget in enumerate(self._meter_widgets):
            if index < len(meters):
                widget.set_meter(meters[index])
                widget.show()
            else:
                widget.hide()
        detail = provider.get("detail")
        self._detail.setText(str(detail) if detail else "")
        self._detail.setVisible(bool(detail))
        lines = provider.get("lines") or []
        while len(self._line_widgets) < len(lines):
            line = _Line(self)
            self._lines.addWidget(line)
            self._line_widgets.append(line)
        for index, widget in enumerate(self._line_widgets):
            if index < len(lines):
                widget.set_line(lines[index])
                widget.show()
            else:
                widget.hide()
        note = provider.get("note")
        self._note.setText(str(note) if note and provider.get("status") != "ok" else "")
        self._note.setVisible(bool(note) and provider.get("status") != "ok")


class _Meter(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        row = QHBoxLayout()
        self._label = Text("", THEME.text_faint, THEME.font_size_sm, parent=self)
        self._pct = Text("n/a", THEME.text, THEME.font_size_sm, bold=True, parent=self)
        row.addWidget(self._label, 1)
        row.addWidget(self._pct)
        layout.addLayout(row)
        self._bar = Bar(self, height=6)
        layout.addWidget(self._bar)

    def set_meter(self, meter: dict) -> None:
        self._label.setText(str(meter.get("label") or ""))
        pct = meter.get("pct")
        self._pct.setText(f"{round(pct)}%" if _has_pct(pct) else "n/a")
        self._bar.set_value(float(pct) if _has_pct(pct) else 0)
        self._bar.set_fill(_bar_color(pct))


class _Line(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._label = ElideText("", THEME.text_faint, THEME.font_size_sm, parent=self)
        self._value = ElideText("", THEME.text, THEME.font_size_sm, parent=self)
        layout.addWidget(self._label)
        layout.addWidget(self._value, 1)

    def set_line(self, line: dict) -> None:
        self._label.setText(str(line.get("label") or ""))
        self._value.setText(str(line.get("value") or ""))
        tone = line.get("tone")
        if tone == "bad":
            self._value.set_color(THEME.accent_red)
        elif tone == "good":
            self._value.set_color(THEME.accent_green)
        else:
            self._value.set_color(THEME.text)


def _has_pct(pct) -> bool:
    return isinstance(pct, (int, float)) and math.isfinite(pct)


def _bar_color(pct) -> str:
    if not _has_pct(pct):
        return THEME.accent_cyan
    if pct >= 90:
        return THEME.accent_red
    if pct >= 70:
        return THEME.accent_amber
    return THEME.accent_green
