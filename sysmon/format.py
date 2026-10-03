"""Human-readable formatting helpers."""

from __future__ import annotations

import math


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def fmt_kb(kb: float) -> str:
    if not math.isfinite(kb):
        return "n/a"
    abs_kb = abs(kb)
    if abs_kb < 1024:
        return f"{round(kb)} kB"
    if abs_kb < 1024 * 1024:
        decimals = 2 if abs_kb < 10 * 1024 else 1
        return f"{kb / 1024:.{decimals}f} MB"
    if abs_kb < 1024 * 1024 * 1024:
        return f"{kb / (1024 * 1024):.1f} GB"
    return f"{kb / (1024 * 1024 * 1024):.1f} TB"


def fmt_bytes(value: float) -> str:
    return fmt_kb(value / 1024)


def fmt_rate_kbps(kbps: float) -> str:
    if not math.isfinite(kbps):
        return "n/a"
    return f"{kbps / 1024:.1f} MB/s"


def fmt_pct(percent: float) -> str:
    if not math.isfinite(percent):
        return "n/a"
    return f"{round(percent)}%"


def fmt_mhz(mhz: float) -> str:
    if not math.isfinite(mhz) or mhz <= 0:
        return "n/a"
    if mhz >= 1000:
        return f"{mhz / 1000:.1f} GHz"
    return f"{round(mhz)} MHz"


def fmt_temp_c(celsius: float) -> str:
    if not math.isfinite(celsius) or celsius <= 0:
        return "n/a"
    return f"{round(celsius)}°C"


def fmt_usd(amount: float) -> str:
    if not math.isfinite(amount):
        return "n/a"
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):.2f}"
