"""User-tunable knobs. Nothing else may hardcode intervals, sizes, or thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Config:
    # Poll intervals (ms). Kept modest per the bounded-polling budget.
    meminfo_interval_ms: int = 1000
    cpu_interval_ms: int = 1000
    swap_interval_ms: int = 2000
    disk_io_interval_ms: int = 2000
    vram_interval_ms: int = 5000
    vram_apps_interval_ms: int = 10000
    vram_collapsed_interval_ms: int = 15000
    cpuinfo_interval_ms: int = 2000
    static_interval_ms: int = 10000
    storage_interval_ms: int = 5000
    ai_spend_interval_ms: int = 300_000
    ai_spend_collapsed_interval_ms: int = 900_000

    # Swap attribution: rate above this (kB/s) is flagged as real disk swap-out.
    disk_swap_alert_kbps: float = 0.0

    # VRAM card: how many top consumers to list.
    top_processes: int = 1

    # Window geometry (logical px). The grid fills this box.
    window_width: int = 1180
    window_height: int = 760
    window_min_width: int = 880
    window_min_height: int = 560

    # zram devices to track (missing ones render "no zram configured").
    zram_devices: list[str] = field(default_factory=lambda: ["zram0"])


CONFIG = Config()
