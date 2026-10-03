from __future__ import annotations

from .. import parse
from ..io import read_text
from .base import Collector


class ZramCollector(Collector):
    def __init__(self, config, parent=None) -> None:
        super().__init__(config, parent)
        self.exists = False
        self.device = ""
        self.orig_bytes = 0.0
        self.compr_bytes = 0.0
        self.mem_used_bytes = 0.0
        self.huge_pages = 0.0
        self.zram_swap_used_kb = 0.0
        self.zram_swap_size_kb = 0.0
        self.zswap_status = "n/a"
        self.writeback_status = "n/a"
        self.reads_completed = 0.0
        self.writes_completed = 0.0
        self._poll_timer = self._start_timer(config.swap_interval_ms, self.poll)
        self._static_timer = self._start_timer(config.static_interval_ms, self.poll_static)

    @property
    def ratio(self) -> float:
        return self.orig_bytes / self.compr_bytes if self.compr_bytes > 0 else 0.0

    @property
    def ram_saved_bytes(self) -> float:
        return max(0.0, self.orig_bytes - self.mem_used_bytes)

    @property
    def ready(self) -> bool:
        return self.exists and self.mem_used_bytes > 0

    def poll(self) -> None:
        device = self.config.zram_devices[0] if self.config.zram_devices else "zram0"
        mm = read_text(f"/sys/block/{device}/mm_stat")
        if mm is None:
            self.exists = False
        else:
            fields = parse.parse_mm_stat(mm)
            if len(fields) < 3:
                self.exists = False
            else:
                self.exists = True
                self.device = device
                self.orig_bytes = fields[0]
                self.compr_bytes = fields[1]
                self.mem_used_bytes = fields[2]
                self.huge_pages = fields[6] if len(fields) > 6 else 0.0

        stat = read_text(f"/sys/block/{device}/stat")
        if stat:
            diskstat = parse.parse_diskstat(stat)
            if len(diskstat) >= 6:
                self.reads_completed = diskstat[0]
                self.writes_completed = diskstat[3]

        swaps = read_text("/proc/swaps")
        self.zram_swap_size_kb = 0.0
        self.zram_swap_used_kb = 0.0
        if swaps:
            for area in parse.parse_swaps(swaps):
                if area["isZram"]:
                    self.zram_swap_size_kb = area["sizeKB"]
                    self.zram_swap_used_kb = area["usedKB"]
                    break
        self.updated.emit()

    def poll_static(self) -> None:
        device = self.config.zram_devices[0] if self.config.zram_devices else "zram0"
        zswap = read_text("/sys/module/zswap/parameters/enabled")
        if zswap is None:
            self.zswap_status = "n/a"
        else:
            self.zswap_status = "On" if zswap.strip() == "Y" else "Off"
        backing = read_text(f"/sys/block/{device}/backing_dev")
        if backing is None:
            self.writeback_status = "n/a"
        else:
            trimmed = backing.strip()
            self.writeback_status = "none" if trimmed == "none" else trimmed
        self.updated.emit()
