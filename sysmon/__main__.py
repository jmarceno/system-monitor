"""Launch the system monitor, or run a headless collector check."""

from __future__ import annotations

import argparse
import json
import math
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from . import format as fmt
from .config import CONFIG
from .snapshot import Snapshot
from .state import WindowState
from .ui.window import MonitorWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wayland system monitor")
    parser.add_argument("--check", action="store_true", help="headless collector dump (no window)")
    parser.add_argument("--check-ms", type=int, default=6000, help="how long --check waits for samples")
    args = parser.parse_args(argv)

    if args.check:
        return _run_check(args.check_ms)

    app = QApplication(sys.argv)
    app.setApplicationName("system-monitor")
    app.setApplicationDisplayName("System Monitor")
    app.setDesktopFileName("system-monitor")
    app.setQuitOnLastWindowClosed(True)
    snapshot = Snapshot(CONFIG, app)
    state = WindowState.load()
    window = MonitorWindow(snapshot, state)
    window.show()
    return app.exec()


def _run_check(wait_ms: int) -> int:
    app = QApplication(sys.argv)
    snapshot = Snapshot(CONFIG, app)

    def dump() -> None:
        mem = snapshot.mem
        cpu = snapshot.cpu
        zram = snapshot.zram
        swap = snapshot.swap
        print("=== MemInfo ===")
        print(
            "used:", fmt.fmt_kb(mem.used_kb), "/", fmt.fmt_kb(mem.total_kb),
            f"({fmt.fmt_pct(mem.used_pct)})",
            "avail:", fmt.fmt_kb(mem.available_kb),
            "cache:", fmt.fmt_kb(mem.cache_kb),
            "buffers:", fmt.fmt_kb(mem.buffers_kb),
            "pressure:", mem.pressure_pct,
        )
        print("=== Cpu ===")
        print("busy:", fmt.fmt_pct(cpu.busy_pct), "mhz:", fmt.fmt_mhz(cpu.mhz), "temp:", fmt.fmt_temp_c(cpu.temp_c))
        print("=== Zram ===")
        print(
            "exists:", zram.exists, zram.device,
            "orig:", fmt.fmt_bytes(zram.orig_bytes),
            "compr:", fmt.fmt_bytes(zram.compr_bytes),
            "memUsed:", fmt.fmt_bytes(zram.mem_used_bytes),
            "ratio:", f"{zram.ratio:.2f}x",
            "swapUsed:", fmt.fmt_kb(zram.zram_swap_used_kb), "/", fmt.fmt_kb(zram.zram_swap_size_kb),
            "zswap:", zram.zswap_status, "writeback:", zram.writeback_status,
            "wPages:", zram.writes_completed,
        )
        print("=== SwapDisk ===")
        print("areas:", json.dumps(_jsonable(swap.areas)))
        print(
            "zram:", fmt.fmt_kb(swap.zram_used_kb), "/", fmt.fmt_kb(swap.zram_size_kb),
            "disk:", fmt.fmt_kb(swap.disk_used_kb), "/", fmt.fmt_kb(swap.disk_size_kb),
        )
        print(
            "rates: zramOut", fmt.fmt_rate_kbps(swap.zram_swap_out_kbps),
            "diskOut", fmt.fmt_rate_kbps(swap.disk_swap_out_kbps),
            "zramIn", fmt.fmt_rate_kbps(swap.zram_swap_in_kbps),
            "diskIn", fmt.fmt_rate_kbps(swap.disk_swap_in_kbps),
        )
        print("verdict:", swap.verdict_text)
        print("=== StorageIo ===")
        print("samples:", json.dumps(_jsonable(snapshot.storage_io.samples)))
        print("=== Vram ===")
        print(
            "avail:", snapshot.vram.available,
            fmt.fmt_kb(snapshot.vram.gpu_used_mib * 1024), "/",
            fmt.fmt_kb(snapshot.vram.gpu_total_mib * 1024),
            f"({fmt.fmt_pct(snapshot.vram.used_pct)})",
        )
        print("gpus:", json.dumps(_jsonable(snapshot.vram.gpus)))
        print("temps:", json.dumps(_jsonable(snapshot.vram.temps)))
        print("procs:", json.dumps(_jsonable(snapshot.vram.procs)))
        print("=== Storage ===")
        print("ready:", snapshot.storage.ready, "volumes:", json.dumps(_jsonable(snapshot.storage.volumes)))
        print("=== AiSpend ===")
        print(
            "ready:", snapshot.ai_spend.ready,
            "ok:", snapshot.ai_spend.ok_count,
            "failed:", snapshot.ai_spend.query_failed,
        )
        print("providers:", json.dumps(_jsonable(snapshot.ai_spend.providers)))
        print("=== ALL CHECKS DONE ===")
        app.quit()

    QTimer.singleShot(wait_ms, dump)
    return app.exec()


def _jsonable(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
