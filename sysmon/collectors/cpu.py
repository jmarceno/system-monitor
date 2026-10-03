from __future__ import annotations

import math
from pathlib import Path

from .. import parse
from ..format import clamp
from ..io import read_text
from .base import Collector


class CpuCollector(Collector):
    def __init__(self, config, parent=None) -> None:
        super().__init__(config, parent)
        self.busy_pct = 0.0
        self.mhz = 0.0
        self.temp_c = math.nan
        self._prev: dict[str, float] | None = None
        self._temp_path: str | None = None
        self._resolve_hwmon()
        self._stat_timer = self._start_timer(config.cpu_interval_ms, self.poll_stat)
        self._info_timer = self._start_timer(config.cpuinfo_interval_ms, self.poll_info)

    @property
    def ready(self) -> bool:
        return self._prev is not None and self.mhz > 0

    def _on_compact_changed(self) -> None:
        if self._compact:
            self._stat_timer.stop()
            self._info_timer.stop()
        else:
            self._stat_timer.start()
            self._info_timer.start()

    def _resolve_hwmon(self) -> None:
        hwmon = Path("/sys/class/hwmon")
        if not hwmon.is_dir():
            return
        for entry in sorted(hwmon.glob("hwmon*")):
            name = read_text(entry / "name")
            if name and parse.is_cpu_hwmon_name(name.strip()):
                self._temp_path = str(entry / "temp1_input")
                return

    def poll_stat(self) -> None:
        text = read_text("/proc/stat")
        if not text:
            return
        jiffies = parse.parse_cpu(text)
        if len(jiffies) < 5:
            return
        total = sum(jiffies)
        idle = jiffies[3] + jiffies[4]
        if self._prev:
            delta_total = total - self._prev["total"]
            delta_idle = idle - self._prev["idle"]
            self.busy_pct = clamp(100.0 * (delta_total - delta_idle) / delta_total, 0, 100) if delta_total > 0 else 0.0
        self._prev = {"total": total, "idle": idle}
        self.updated.emit()

    def poll_info(self) -> None:
        cpuinfo = read_text("/proc/cpuinfo")
        if cpuinfo:
            self.mhz = parse.parse_cpu_mhz(cpuinfo)
        if self._temp_path:
            milli = read_text(self._temp_path)
            self.temp_c = parse.parse_temp_milli(milli) if milli is not None else math.nan
        self.updated.emit()
