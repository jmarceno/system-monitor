from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from ..lib import ai_spend_collect
from .base import Collector


class _SpendWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            snapshot = ai_spend_collect.collect()
        except Exception as exc:  # noqa: BLE001 — collector already degrades; never crash the UI
            self.failed.emit(str(exc) or "unavailable")
            return
        self.finished.emit(snapshot)


class AiSpendCollector(Collector):
    def __init__(self, config, parent=None) -> None:
        super().__init__(config, parent)
        self.providers: list[dict[str, Any]] = []
        self.ok_count = 0
        self.generated_at = ""
        self.ready = False
        self.query_failed = False
        self.fail_note = ""
        self._thread: QThread | None = None
        self._worker: _SpendWorker | None = None
        self._timer = self._start_timer(config.ai_spend_interval_ms, self.poll)

    def _on_compact_changed(self) -> None:
        interval = (
            self.config.ai_spend_collapsed_interval_ms
            if self._compact
            else self.config.ai_spend_interval_ms
        )
        self._timer.setInterval(interval)

    def poll(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        thread = QThread(self)
        worker = _SpendWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_snapshot)
        worker.failed.connect(self._on_fail)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_thread)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _clear_thread(self) -> None:
        self._thread = None
        self._worker = None

    def _on_snapshot(self, snapshot: object) -> None:
        if not isinstance(snapshot, dict):
            self._on_fail("snapshot parse failed")
            return
        providers = snapshot.get("providers")
        self.providers = providers if isinstance(providers, list) else []
        ok = snapshot.get("okCount")
        self.ok_count = int(ok) if isinstance(ok, (int, float)) else 0
        generated = snapshot.get("generatedAt")
        self.generated_at = generated if isinstance(generated, str) else ""
        self.ready = True
        self.query_failed = False
        self.fail_note = ""
        self.updated.emit()

    def _on_fail(self, note: str) -> None:
        self.ready = False
        self.query_failed = True
        self.fail_note = note or "unavailable"
        self.providers = []
        self.ok_count = 0
        self.updated.emit()
