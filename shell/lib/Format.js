// Human-readable formatting helpers.
.pragma library

function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
}

// kB -> "185 MB" / "6.2 GB" / "1.2 TB" (kB as the smallest unit, /proc convention)
function fmtKB(kb) {
    if (!isFinite(kb))
        return "n/a";
    const abs = Math.abs(kb);
    if (abs < 1024)
        return Math.round(kb) + " kB";
    if (abs < 1024 * 1024)
        return (kb / 1024).toFixed(abs < 10 * 1024 ? 2 : 1) + " MB";
    if (abs < 1024 * 1024 * 1024)
        return (kb / (1024 * 1024)).toFixed(1) + " GB";
    return (kb / (1024 * 1024 * 1024)).toFixed(1) + " TB";
}

// bytes -> same scale as fmtKB
function fmtBytes(b) {
    return fmtKB(b / 1024);
}

// kB/s -> "0 MB/s" / "12.4 MB/s"
function fmtRateKBps(kbps) {
    if (!isFinite(kbps))
        return "n/a";
    return (kbps / 1024).toFixed(1) + " MB/s";
}

function fmtPct(p) {
    if (!isFinite(p))
        return "n/a";
    return Math.round(p) + "%";
}

// MHz -> "2.1 GHz" / "845 MHz"
function fmtMHz(mhz) {
    if (!isFinite(mhz) || mhz <= 0)
        return "n/a";
    if (mhz >= 1000)
        return (mhz / 1000).toFixed(1) + " GHz";
    return Math.round(mhz) + " MHz";
}
