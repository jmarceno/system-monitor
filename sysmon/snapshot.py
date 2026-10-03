"""Aggregates collectors. UI never reads /proc or /sys."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .collectors import (
    AiSpendCollector,
    CpuCollector,
    MemInfoCollector,
    StorageCollector,
    StorageIoCollector,
    SwapDiskCollector,
    VramCollector,
    ZramCollector,
)
from .config import Config


class Snapshot(QObject):
    updated = Signal()

    def __init__(self, config: Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.mem = MemInfoCollector(config, self)
        self.cpu = CpuCollector(config, self)
        self.zram = ZramCollector(config, self)
        self.swap = SwapDiskCollector(config, self.zram, self)
        self.vram = VramCollector(config, self)
        self.storage = StorageCollector(config, self)
        self.storage_io = StorageIoCollector(config, self.storage, self)
        self.ai_spend = AiSpendCollector(config, self)
        self._compact = False
        for collector in (
            self.mem,
            self.cpu,
            self.zram,
            self.swap,
            self.vram,
            self.storage,
            self.storage_io,
            self.ai_spend,
        ):
            collector.updated.connect(self.updated)

    @property
    def compact_mode(self) -> bool:
        return self._compact

    @compact_mode.setter
    def compact_mode(self, value: bool) -> None:
        self._compact = bool(value)
        for collector in (
            self.mem,
            self.cpu,
            self.zram,
            self.swap,
            self.vram,
            self.storage,
            self.storage_io,
            self.ai_spend,
        ):
            collector.set_compact(self._compact)
