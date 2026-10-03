from __future__ import annotations

from typing import Any

from .. import parse
from ..io import read_text
from .base import Collector


class SwapDiskCollector(Collector):
    """Swap attribution: zram (in-RAM) vs real disk swap. See PLAN.md §4.3."""

    VERDICTS = ("idle", "zram-only", "draining", "disk-pressure")

    def __init__(self, config, zram, parent=None) -> None:
        super().__init__(config, parent)
        self._zram = zram
        self.areas: list[dict[str, Any]] = []
        self.zram_size_kb = 0.0
        self.zram_used_kb = 0.0
        self.disk_size_kb = 0.0
        self.disk_used_kb = 0.0
        self.disk_swap_out_kbps = 0.0
        self.disk_swap_in_kbps = 0.0
        self.zram_swap_out_kbps = 0.0
        self.zram_swap_in_kbps = 0.0
        self.verdict = 0
        self._prev: dict[str, Any] | None = None
        self._timer = self._start_timer(config.swap_interval_ms, self.poll)

    @property
    def verdict_text(self) -> str:
        return self.VERDICTS[self.verdict]

    @property
    def total_size_kb(self) -> float:
        """zram plus disk, for diagnostics. The swap UI uses ``disk_size_kb`` only."""
        return self.zram_size_kb + self.disk_size_kb

    @property
    def total_used_kb(self) -> float:
        """zram plus disk, for diagnostics. The swap UI uses ``disk_used_kb`` only."""
        return self.zram_used_kb + self.disk_used_kb

    @property
    def used_pct(self) -> float:
        """Real disk swap only. zram is not swap pressure (PLAN.md §4.3)."""
        if self.disk_size_kb <= 0:
            return 0.0
        return 100.0 * self.disk_used_kb / self.disk_size_kb

    @property
    def has_sample(self) -> bool:
        return self._prev is not None

    def poll(self) -> None:
        vmstat = read_text("/proc/vmstat")
        swaps = read_text("/proc/swaps")
        vm = parse.pair_map(vmstat)
        areas = parse.parse_swaps(swaps)
        for area in areas:
            area["usedDeltaKB"] = 0.0
        zram_used = sum(item["usedKB"] for item in areas if item["isZram"])
        zram_size = sum(item["sizeKB"] for item in areas if item["isZram"])
        disk_used = sum(item["usedKB"] for item in areas if not item["isZram"])
        disk_size = sum(item["sizeKB"] for item in areas if not item["isZram"])

        now = {
            "pswpin": vm.get("pswpin", 0.0),
            "pswpout": vm.get("pswpout", 0.0),
            "zramR": self._zram.reads_completed,
            "zramW": self._zram.writes_completed,
            "zramUsed": zram_used,
            "diskUsed": disk_used,
        }

        if self._prev and self.config.swap_interval_ms > 0:
            sec = self.config.swap_interval_ms / 1000
            pswpin_d = max(0.0, now["pswpin"] - self._prev["pswpin"])
            pswpout_d = max(0.0, now["pswpout"] - self._prev["pswpout"])
            zram_rd = max(0.0, now["zramR"] - self._prev["zramR"])
            zram_wd = max(0.0, now["zramW"] - self._prev["zramW"])

            # pages are 4 KiB. zram counters are page counts (4 KiB writes).
            self.zram_swap_in_kbps = 4 * min(zram_rd, pswpin_d) / sec
            self.zram_swap_out_kbps = 4 * min(zram_wd, pswpout_d) / sec
            self.disk_swap_in_kbps = max(0.0, 4 * (pswpin_d - zram_rd) / sec)
            self.disk_swap_out_kbps = max(0.0, 4 * (pswpout_d - zram_wd) / sec)

            prev_areas = self._prev.get("areas") or []
            for area in areas:
                if area["isZram"]:
                    area["usedDeltaKB"] = zram_used - self._prev["zramUsed"]
                else:
                    area["usedDeltaKB"] = self._delta_for(area, prev_areas)

            disk_grow = now["diskUsed"] - self._prev["diskUsed"]
            zram_grow = now["zramUsed"] - self._prev["zramUsed"]
            # No disk swap device means the disk rate is zero, even if vmstat
            # and zram counters disagree by a page. zram traffic stays on the
            # zram fields above.
            if disk_size <= 0:
                self.disk_swap_in_kbps = 0.0
                self.disk_swap_out_kbps = 0.0
                disk_grow = 0.0
            if self.disk_swap_out_kbps > self.config.disk_swap_alert_kbps or disk_grow > 0:
                self.verdict = 3
            elif zram_grow > 0:
                self.verdict = 1
            elif disk_grow < 0 or zram_grow < 0:
                self.verdict = 2
            else:
                self.verdict = 0

        now["areas"] = areas
        self._prev = now
        self.areas = areas
        self.zram_used_kb = zram_used
        self.zram_size_kb = zram_size
        self.disk_used_kb = disk_used
        self.disk_size_kb = disk_size
        self.updated.emit()

    def _delta_for(self, area: dict[str, Any], prev_areas: list[dict[str, Any]]) -> float:
        for prev in prev_areas:
            if prev.get("name") == area["name"]:
                return area["usedKB"] - prev["usedKB"]
        return 0.0
