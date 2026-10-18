"""VRAM totals and the heaviest consumer.

NVIDIA (when `nvidia-smi` is on PATH): read-only `--query-gpu` / `--query-compute-apps`.
AMD amdgpu: `/sys/class/drm/cardN/device/mem_info_vram_{used,total}` (bytes),
edge temperature from the amdgpu hwmon, and per-process `drm-resident-vram`
in `/proc/<pid>/fdinfo`. The fdinfo walk runs on a worker thread.

Both can be present at once. The ring and the card header sum used/total;
each GPU keeps its own bar and temperature. Per-process bytes are not the
GPU total (shared buffers and driver-reserved memory).
"""

from __future__ import annotations

import logging
import math
import os
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QThread, Signal

from .. import parse
from ..io import read_text
from .base import Collector

log = logging.getLogger(__name__)

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
_PCI_IDS = (
    Path("/usr/share/hwdata/pci.ids"),
    Path("/usr/share/misc/pci.ids"),
)
_MIB = 1024 * 1024


class _AmdProcWorker(QObject):
    finished = Signal(object)

    def run(self) -> None:
        try:
            procs = scan_amd_processes()
        except Exception:
            log.exception("system-monitor: amdgpu process scan failed")
            procs = []
        self.finished.emit(procs)


class VramCollector(Collector):
    def __init__(self, config, parent=None) -> None:
        super().__init__(config, parent)
        self.gpu_used_mib = 0.0
        self.gpu_total_mib = 0.0
        self.temp_c = math.nan
        self.gpus: list[dict[str, Any]] = []
        self.temps: list[float] = []
        self.procs: list[dict[str, Any]] = []
        self._nvidia_bin = shutil.which("nvidia-smi") is not None
        self._nvidia_failed = False
        self._amd_polled = False
        self._unavailable = False
        self._logged_unavailable = False
        self._amd_gpus: list[dict[str, Any]] = []
        self._nvidia_gpus: list[dict[str, Any]] = []
        self._amd_procs: list[dict[str, Any]] = []
        self._nvidia_procs: list[dict[str, Any]] = []
        self._amd_names: dict[str, str] | None = None
        self._gpu_proc = QProcess(self)
        self._apps_proc = QProcess(self)
        self._gpu_proc.finished.connect(self._on_gpu_finished)
        self._apps_proc.finished.connect(self._on_apps_finished)
        self._thread: QThread | None = None
        self._worker: _AmdProcWorker | None = None
        self._gpu_timer = self._start_timer(config.vram_interval_ms, self.poll_gpu)
        self._apps_timer = self._start_timer(config.vram_apps_interval_ms, self.poll_apps)

    @property
    def used_pct(self) -> float:
        return 100.0 * self.gpu_used_mib / self.gpu_total_mib if self.gpu_total_mib > 0 else 0.0

    @property
    def available(self) -> bool:
        return self.gpu_total_mib > 0

    @property
    def nvidia_failed(self) -> bool:
        return self._unavailable and self._nvidia_bin and not self._amd_gpus

    @property
    def card_title(self) -> str:
        vendors = {str(gpu.get("vendor") or "") for gpu in self.gpus}
        if vendors == {"amd"}:
            return "AMD VRAM"
        if vendors == {"nvidia"}:
            return "NVIDIA VRAM"
        return "GPU VRAM"

    @property
    def status_note(self) -> str:
        if self._unavailable:
            if self.nvidia_failed:
                return "nvidia-smi unavailable — VRAM card disabled"
            return "GPU telemetry unavailable — VRAM card disabled"
        if self._amd_gpus or not self._nvidia_bin:
            return "querying GPU…"
        return "querying nvidia-smi…"

    def _on_compact_changed(self) -> None:
        interval = self.config.vram_collapsed_interval_ms if self._compact else self.config.vram_interval_ms
        apps_interval = self.config.vram_collapsed_interval_ms if self._compact else self.config.vram_apps_interval_ms
        self._gpu_timer.setInterval(interval)
        self._apps_timer.setInterval(apps_interval)

    def poll_gpu(self) -> None:
        self._poll_amd_gpu()
        if not self._nvidia_bin:
            return
        if self._gpu_proc.state() != QProcess.ProcessState.NotRunning:
            return
        self._gpu_proc.start(GPU_QUERY[0], GPU_QUERY[1:])

    def poll_apps(self) -> None:
        self._poll_amd_apps()
        if not self._nvidia_bin:
            return
        if self._apps_proc.state() != QProcess.ProcessState.NotRunning:
            return
        self._apps_proc.start(APPS_QUERY[0], APPS_QUERY[1:])

    def _poll_amd_gpu(self) -> None:
        self._amd_gpus = read_amd_gpus(self._pci_names())
        self._amd_polled = True
        self._compose_gpus()
        self._settle()

    def _poll_amd_apps(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        thread = QThread(self)
        worker = _AmdProcWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_amd_procs)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_thread)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _clear_thread(self) -> None:
        self._thread = None
        self._worker = None

    def _on_amd_procs(self, procs: object) -> None:
        self._amd_procs = procs if isinstance(procs, list) else []
        self._compose_procs()

    def _pci_names(self) -> dict[str, str]:
        if self._amd_names is not None:
            return self._amd_names
        text = None
        for path in _PCI_IDS:
            text = read_text(path)
            if text:
                break
        self._amd_names = parse.parse_pci_vendor_devices(text, "1002")
        return self._amd_names

    def _on_gpu_finished(self, exit_code: int, _status) -> None:
        output = bytes(self._gpu_proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if exit_code != 0:
            self._fail_nvidia()
            return
        parsed = parse.parse_nvidia_gpus(output)
        if not parsed:
            self._fail_nvidia()
            return
        self._nvidia_failed = False
        painted: list[dict[str, Any]] = []
        for gpu in parsed:
            temp = gpu["tempC"] if math.isfinite(gpu["tempC"]) and gpu["tempC"] > 0 else math.nan
            total = gpu["totalMiB"]
            used = gpu["usedMiB"]
            painted.append({
                "vendor": "nvidia",
                "index": gpu["index"],
                "name": gpu["name"],
                "shortName": gpu["shortName"],
                "usedMiB": used,
                "totalMiB": total,
                "tempC": temp,
                "usedPct": 100.0 * used / total if total > 0 else 0.0,
            })
        self._nvidia_gpus = painted
        self._compose_gpus()

    def _on_apps_finished(self, exit_code: int, _status) -> None:
        output = bytes(self._apps_proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if exit_code != 0:
            self._nvidia_procs = []
            self._compose_procs()
            return
        entries = []
        for entry in parse.parse_nvidia_apps(output):
            if _pid_matches(entry["pid"], entry["name"]):
                entries.append(entry)
        self._nvidia_procs = entries
        self._compose_procs()

    def _compose_gpus(self) -> None:
        used = 0.0
        total = 0.0
        max_temp = math.nan
        temps: list[float] = []
        painted: list[dict[str, Any]] = []
        for gpu in [*self._amd_gpus, *self._nvidia_gpus]:
            used += float(gpu["usedMiB"])
            total += float(gpu["totalMiB"])
            temp = gpu["tempC"]
            if isinstance(temp, (int, float)) and math.isfinite(temp) and (not math.isfinite(max_temp) or temp > max_temp):
                max_temp = temp
            temps.append(temp if isinstance(temp, (int, float)) else math.nan)
            painted.append(gpu)
        self.gpus = painted
        self.temps = temps
        self.gpu_used_mib = used
        self.gpu_total_mib = total
        self.temp_c = max_temp
        if total > 0:
            self._unavailable = False
        self.updated.emit()

    def _compose_procs(self) -> None:
        entries = [*self._amd_procs, *self._nvidia_procs]
        entries.sort(key=lambda item: float(item.get("mib") or 0), reverse=True)
        top = [dict(item) for item in entries[: self.config.top_processes]]
        seen: dict[str, int] = {}
        for item in top:
            name = str(item.get("name") or "")
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1:
                item["name"] = f"{name} #{seen[name]}"
        self.procs = top
        self.updated.emit()

    def _fail_nvidia(self) -> None:
        self._nvidia_failed = True
        self._nvidia_gpus = []
        self._nvidia_procs = []
        self._compose_gpus()
        self._compose_procs()
        self._settle()

    def _settle(self) -> None:
        nvidia_down = (not self._nvidia_bin) or self._nvidia_failed
        amd_down = self._amd_polled and not self._amd_gpus
        if not (nvidia_down and amd_down and self.gpu_total_mib <= 0):
            return
        if self._unavailable:
            return
        self._unavailable = True
        if not self._logged_unavailable:
            self._logged_unavailable = True
            log.warning("system-monitor: no NVIDIA or AMD VRAM source; VRAM card unavailable")
        self.updated.emit()


def read_amd_gpus(names: dict[str, str]) -> list[dict[str, Any]]:
    """amdgpu cards only. Connector nodes (`card0-DP-1`) are not GPUs."""
    root = Path("/sys/class/drm")
    if not root.is_dir():
        return []
    found: list[tuple[int, dict[str, Any]]] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return []
    for card in entries:
        if not card.name.startswith("card") or not card.name[4:].isdigit():
            continue
        device = card / "device"
        vendor = (read_text(device / "vendor") or "").strip().lower()
        if vendor != "0x1002":
            continue
        driver = device / "driver"
        try:
            driver_name = os.path.basename(os.readlink(driver))
        except OSError:
            continue
        if driver_name != "amdgpu":
            continue
        total_bytes = parse.to_num((read_text(device / "mem_info_vram_total") or "").strip())
        if total_bytes <= 0:
            continue
        used_bytes = parse.to_num((read_text(device / "mem_info_vram_used") or "").strip())
        device_id = (read_text(device / "device") or "").strip().lower().removeprefix("0x")
        name = names.get(device_id) or "AMD GPU"
        used = used_bytes / _MIB
        total = total_bytes / _MIB
        temp = _amd_edge_temp(device)
        index = int(card.name[4:])
        found.append((index, {
            "vendor": "amd",
            "index": index,
            "name": name,
            "shortName": parse.short_gpu_name(name),
            "usedMiB": used,
            "totalMiB": total,
            "tempC": temp,
            "usedPct": 100.0 * used / total if total > 0 else 0.0,
        }))
    found.sort(key=lambda item: item[0])
    return [gpu for _index, gpu in found]


def _amd_edge_temp(device: Path) -> float:
    """Edge sensor in °C. Junction/hotspot runs hotter and is not the die reading we show for NVIDIA."""
    hwmon = device / "hwmon"
    if not hwmon.is_dir():
        return math.nan
    try:
        mons = list(hwmon.iterdir())
    except OSError:
        return math.nan
    for mon in mons:
        if (read_text(mon / "name") or "").strip() != "amdgpu":
            continue
        edge = math.nan
        fallback = math.nan
        try:
            labels = sorted(mon.glob("temp*_label"))
        except OSError:
            labels = []
        for label_path in labels:
            label = (read_text(label_path) or "").strip().lower()
            number = label_path.name.removeprefix("temp").removesuffix("_label")
            temp = parse.parse_temp_milli(read_text(mon / f"temp{number}_input"))
            if label == "edge" and math.isfinite(temp):
                edge = temp
            elif not math.isfinite(fallback) and math.isfinite(temp):
                fallback = temp
        if math.isfinite(edge):
            return edge
        if math.isfinite(fallback):
            return fallback
        return parse.parse_temp_milli(read_text(mon / "temp1_input"))
    return math.nan


def scan_amd_processes() -> list[dict[str, Any]]:
    """Resident VRAM per pid. Only fds pointing at `/dev/dri` are read."""
    samples: list[dict[str, Any]] = []
    proc = Path("/proc")
    try:
        pids = [entry for entry in proc.iterdir() if entry.name.isdigit()]
    except OSError:
        return []
    for entry in pids:
        fd_dir = entry / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except OSError:
            continue
        pid = int(entry.name)
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if not target.startswith("/dev/dri/"):
                continue
            info = parse.parse_amd_fdinfo(read_text(entry / "fdinfo" / fd.name))
            if info is None or info["vramBytes"] <= 0:
                continue
            client = info["client"] or f"fd:{fd.name}"
            samples.append({
                "pid": pid,
                "pdev": info["pdev"],
                "client": client,
                "vramBytes": info["vramBytes"],
            })
    totals = parse.sum_amd_vram_by_pid(samples)
    procs: list[dict[str, Any]] = []
    for pid, vram_bytes in totals.items():
        comm = read_text(f"/proc/{pid}/comm")
        if comm is None:
            continue
        name = comm.strip()
        if not name:
            continue
        procs.append({
            "pid": pid,
            "mib": vram_bytes / _MIB,
            "name": name,
            "rawName": name,
        })
    return procs


def _pid_matches(pid: int, basename: str) -> bool:
    comm = read_text(f"/proc/{pid}/comm")
    if comm is None:
        return False
    comm = comm.strip()
    return bool(comm) and (basename.startswith(comm) or comm.startswith(basename))
