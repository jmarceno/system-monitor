"""Resizable desktop window. One grid, shared edges, no floating panels."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ..config import CONFIG
from ..snapshot import Snapshot
from ..state import WindowState
from ..theme import THEME
from .cards import MemoryCard, SwapAttributionCard, VramCard, ZramCard
from .gauges import SummaryGauges
from .sidecars import AiSpendSidecar, StorageSidecar
from .widgets import GridCell


class MonitorWindow(QWidget):
    def __init__(self, snapshot: Snapshot, state: WindowState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snap = snapshot
        self._state = state
        self.setWindowTitle("System Monitor")
        self.setObjectName("system-monitor")
        self.setMinimumSize(CONFIG.window_min_width, CONFIG.window_min_height)
        self.resize(state.width or CONFIG.window_width, state.height or CONFIG.window_height)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(THEME.window_bg))
        self.setPalette(palette)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._state.save)
        self._placed = False

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        for column in range(4):
            grid.setColumnStretch(column, 1)

        self._gauges = SummaryGauges(snapshot, self)
        for column, gauge in enumerate((self._gauges.cpu, self._gauges.gpu, self._gauges.ram, self._gauges.swap)):
            cell = GridCell(self, min_height=96, grow=False)
            cell.add(gauge, 1)
            grid.addWidget(cell, 0, column)
        grid.setRowStretch(0, 0)

        self._memory = MemoryCard(snapshot, self)
        self._zram = ZramCard(snapshot, self)
        self._swap = SwapAttributionCard(snapshot, self)
        self._vram = VramCard(snapshot, self)
        self._storage = StorageSidecar(snapshot, self)
        self._spend = AiSpendSidecar(snapshot, self)

        # Each column sizes its summary sections to their content. Storage and
        # AI spend take the height those sections don't use.
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        left.addWidget(self._memory, 0)
        left.addWidget(self._swap, 0)
        left.addWidget(self._storage, 1)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._zram, 0)
        right.addWidget(self._vram, 0)
        right.addWidget(self._spend, 1)
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)
        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        body = QWidget(self)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.setLayout(columns)
        grid.addWidget(body, 1, 0, 1, 4)
        grid.setRowStretch(1, 1)

        snapshot.updated.connect(self.refresh)
        self.refresh()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(THEME.window_bg))

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        if self._placed:
            self._remember_geometry()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._placed:
            self._remember_geometry()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._placed:
            self._fit_screen()
            self._placed = True

    def refresh(self) -> None:
        self._gauges.refresh()
        self._memory.refresh()
        self._swap.refresh()
        self._zram.refresh()
        self._vram.refresh()
        self._storage.refresh()
        self._spend.refresh()

    def _remember_geometry(self) -> None:
        self._state.pos_x = self.x()
        self._state.pos_y = self.y()
        self._state.width = self.width()
        self._state.height = self.height()
        screen = QGuiApplication.screenAt(self.pos()) or self.screen()
        if screen is not None:
            self._state.screen_name = screen.name()
        self._save_timer.start()

    def _fit_screen(self) -> None:
        origin = QPoint(self._state.pos_x, self._state.pos_y)
        screen = QGuiApplication.screenAt(origin) or self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.move(origin)
            return
        geo = screen.availableGeometry()
        min_w = min(self.minimumWidth(), geo.width())
        min_h = min(self.minimumHeight(), geo.height())
        if min_w != self.minimumWidth() or min_h != self.minimumHeight():
            self.setMinimumSize(min_w, min_h)
        width = min(max(self.width(), min_w), geo.width())
        height = min(max(self.height(), min_h), geo.height())
        self.resize(width, height)
        x = max(geo.x(), min(origin.x(), geo.right() - self.width() + 1))
        y = max(geo.y(), min(origin.y(), geo.bottom() - self.height() + 1))
        self.move(x, y)
