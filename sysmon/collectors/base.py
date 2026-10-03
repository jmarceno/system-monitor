from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from ..config import Config


class Collector(QObject):
    """Timer-driven snapshot owner. UI binds to properties and `updated`."""

    updated = Signal()

    def __init__(self, config: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self._compact = False

    def set_compact(self, compact: bool) -> None:
        if self._compact == compact:
            return
        self._compact = compact
        self._on_compact_changed()

    def _on_compact_changed(self) -> None:
        return

    def _start_timer(self, interval_ms: int, callback, start_now: bool = True) -> QTimer:
        timer = QTimer(self)
        timer.setInterval(interval_ms)
        timer.timeout.connect(callback)
        timer.start()
        if start_now:
            QTimer.singleShot(0, callback)
        return timer
