from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QProcess

from .. import parse
from .base import Collector


GPU_QUERY = [
    "nvidia-smi",
    "--query-gpu=memory.used,memory.total,temperature.gpu,index,name",
    "--format=csv,noheader,nounits",
]
APPS_QUERY = [
    "nvidia-smi",
    "--query-compute-apps=pid,used_memory,process_name",
    "--format=csv,noheader,nounits",
]


class VramCollector(Collector):
    def __init__(self, config, parent=None) -> None:
        super().__init__(config, parent)
        self.gpu_used_mib = 0.0
        self.gpu_total_mib = 0.0
        self.temp_c = math.nan
        self.gpus: list[dict[str, Any]] = []
        self.temps: list[float] = []
        self.procs: list[dict[str, Any]] = []
        self.nvidia_failed = False
        self._gpu_proc = QProcess(self)
        self._apps_proc = QProcess(self)
        self._gpu_proc.finished.connect(self._on_gpu_finished)
        self._apps_proc.finished.connect(self._on_apps_finished)
        self._gpu_timer = self._start_timer(config.vram_interval_ms, self.poll_gpu)
        self._apps_timer = self._start_timer(config.vram_apps_interval_ms, self.poll_apps)

    @property
    def used_pct(self) -> float:
        return 100.0 * self.gpu_used_mib / self.gpu_total_mib if self.gpu_total_mib > 0 else 0.0

    @property
    def available(self) -> bool:
        return self.gpu_total_mib > 0

    def _on_compact_changed(self) -> None:
        interval = self.config.vram_collapsed_interval_ms if self._compact else self.config.vram_interval_ms
        apps_interval = self.config.vram_collapsed_interval_ms if self._compact else self.config.vram_apps_interval_ms
        self._gpu_timer.setInterval(interval)
        self._apps_timer.setInterval(apps_interval)

    def poll_gpu(self) -> None:
        if self._gpu_proc.state() != QProcess.ProcessState.NotRunning:
            return
        self._gpu_proc.start(GPU_QUERY[0], GPU_QUERY[1:])

    def poll_apps(self) -> None:
        if self._apps_proc.state() != QProcess.ProcessState.NotRunning:
            return
        self._apps_proc.start(APPS_QUERY[0], APPS_QUERY[1:])

    def _on_gpu_finished(self, exit_code: int, _status) -> None:
        output = bytes(self._gpu_proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if exit_code != 0:
            self._fail()
            return
        gpus = parse.parse_nvidia_gpus(output)
        if not gpus:
            return
        used = 0.0
        total = 0.0
        max_temp = math.nan
        painted: list[dict[str, Any]] = []
        temps: list[float] = []
        for gpu in gpus:
            used += gpu["usedMiB"]
            total += gpu["totalMiB"]
            temp = gpu["tempC"] if math.isfinite(gpu["tempC"]) and gpu["tempC"] > 0 else math.nan
            if math.isfinite(temp) and (not math.isfinite(max_temp) or temp > max_temp):
                max_temp = temp
            temps.append(temp)
            painted.append({
                "index": gpu["index"],
                "name": gpu["name"],
                "shortName": gpu["shortName"],
                "usedMiB": gpu["usedMiB"],
                "totalMiB": gpu["totalMiB"],
                "tempC": temp,
                "usedPct": 100.0 * gpu["usedMiB"] / gpu["totalMiB"] if gpu["totalMiB"] > 0 else 0.0,
            })
        self.gpus = painted
        self.temps = temps
        self.gpu_used_mib = used
        self.gpu_total_mib = total
        self.temp_c = max_temp
        self.updated.emit()

    def _on_apps_finished(self, exit_code: int, _status) -> None:
        output = bytes(self._apps_proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if exit_code != 0:
            self._fail()
            return
        entries = []
        for entry in parse.parse_nvidia_apps(output):
            if self._pid_matches(entry["pid"], entry["name"]):
                entries.append(entry)
        entries.sort(key=lambda item: item["mib"], reverse=True)
        top = entries[: self.config.top_processes]
        seen: dict[str, int] = {}
        for item in top:
            name = item["name"]
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                item["name"] = f"{name} #{seen[name]}"
        self.procs = top
        self.updated.emit()

    def _pid_matches(self, pid: int, basename: str) -> bool:
        from ..io import read_text

        comm = read_text(f"/proc/{pid}/comm")
        if comm is None:
            return False
        comm = comm.strip()
        return bool(comm) and (basename.startswith(comm) or comm.startswith(basename))

    def _fail(self) -> None:
        if self.nvidia_failed:
            return
        self.nvidia_failed = True
        self.updated.emit()
