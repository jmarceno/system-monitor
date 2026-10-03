from __future__ import annotations

from .. import parse
from ..io import read_text
from .base import Collector


class MemInfoCollector(Collector):
    def __init__(self, config, parent=None) -> None:
        super().__init__(config, parent)
        self.total_kb = 0.0
        self.available_kb = 0.0
        self.cache_kb = 0.0
        self.buffers_kb = 0.0
        self.swap_cached_kb = 0.0
        self.swap_total_kb = 0.0
        self.swap_free_kb = 0.0
        self.zswap_kb = 0.0
        self.zswapped_kb = 0.0
        self.pressure_pct = -1.0
        self._timer = self._start_timer(config.meminfo_interval_ms, self.poll)

    @property
    def used_kb(self) -> float:
        return max(0.0, self.total_kb - self.available_kb)

    @property
    def used_pct(self) -> float:
        return 100.0 * self.used_kb / self.total_kb if self.total_kb > 0 else 0.0

    @property
    def ready(self) -> bool:
        return self.total_kb > 0

    def poll(self) -> None:
        meminfo = read_text("/proc/meminfo")
        if meminfo:
            fields = parse.key_value_map(meminfo)
            if fields.get("MemTotal"):
                self.total_kb = fields["MemTotal"]
                self.available_kb = fields["MemAvailable"] if "MemAvailable" in fields else fields.get("MemFree", 0.0)
                self.cache_kb = max(
                    0.0,
                    fields.get("Cached", 0.0) + fields.get("SReclaimable", 0.0) - fields.get("Shmem", 0.0),
                )
                self.buffers_kb = fields.get("Buffers", 0.0)
                self.swap_cached_kb = fields.get("SwapCached", 0.0)
                self.swap_total_kb = fields.get("SwapTotal", 0.0)
                self.swap_free_kb = fields.get("SwapFree", 0.0)
                self.zswap_kb = fields.get("Zswap", 0.0)
                self.zswapped_kb = fields.get("Zswapped", 0.0)
        pressure = read_text("/proc/pressure/memory")
        if pressure is not None:
            self.pressure_pct = parse.parse_pressure_some(pressure)
        self.updated.emit()
