// Pure parsing helpers for /proc, /sys, lsblk and nvidia-smi output.
// Keep these functions side-effect free so they can be tested standalone
// (scripts/parse-test.mjs exercises the same logic in node).
.pragma library

// ---- generic helpers -------------------------------------------------------

function toNum(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
}

function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
}

// "MemTotal:       32786132 kB" lines -> { MemTotal: 32786132, ... }
function keyValueMap(text) {
    const out = {};
    if (!text)
        return out;
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
        const idx = lines[i].indexOf(":");
        if (idx < 0)
            continue;
        const key = lines[i].slice(0, idx).trim();
        const val = lines[i].slice(idx + 1).trim().split(/\s+/)[0];
        out[key] = toNum(val);
    }
    return out;
}

// "key value" whitespace pairs (e.g. /proc/vmstat) -> { pswpin: 123, ... }
function pairMap(text) {
    const out = {};
    if (!text)
        return out;
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
        const parts = lines[i].trim().split(/\s+/);
        if (parts.length >= 2)
            out[parts[0]] = toNum(parts[1]);
    }
    return out;
}

// ---- /proc/swaps -----------------------------------------------------------

// Header line skipped. Returns [{name, type, sizeKB, usedKB, priority}]
function parseSwaps(text) {
    const out = [];
    if (!text)
        return out;
    const lines = text.split("\n");
    for (let i = 1; i < lines.length; i++) {
        const parts = lines[i].trim().split(/\s+/);
        if (parts.length < 5)
            continue;
        out.push({
            name: parts[0],
            type: parts[1],
            sizeKB: toNum(parts[2]),
            usedKB: toNum(parts[3]),
            priority: toNum(parts[4]),
            isZram: parts[0].indexOf("/dev/zram") === 0
        });
    }
    return out;
}

// ---- zram ------------------------------------------------------------------

// /sys/block/zramN/mm_stat -> array of numbers. Field count varies by kernel
// (6..9); callers index defensively. Units: bytes.
// [orig_data_size, compr_data_size, mem_used_total, mem_limit, mem_used_max,
//  same_pages, huge_pages, huge_pages_failed, huge_pages_alloc]
function parseMmStat(text) {
    if (!text)
        return [];
    return text.trim().split(/\s+/).map(toNum);
}

// /sys/block/zramN/stat (diskstat layout):
// [reads completed, reads merged, sectors read, writes completed,
//  writes merged, sectors written, in_flight, io_ticks, ...]
function parseDiskstat(text) {
    if (!text)
        return [];
    return text.trim().split(/\s+/).map(toNum);
}

// ---- /proc/diskstats -------------------------------------------------------

// Whole physical disks only (partitions, zram, loop, dm, md excluded) to
// avoid double counting. Returns [{name, readSectors, writeSectors}]
function parseDiskstats(text) {
    const out = [];
    if (!text)
        return out;
    const lines = text.split("\n");
    const wholeDisk = /^(nvme\d+n\d+|sd[a-z]+|vd[a-z]+|hd[a-z]+|mmcblk\d+|sr\d+)$/;
    for (let i = 0; i < lines.length; i++) {
        const parts = lines[i].trim().split(/\s+/);
        if (parts.length < 10)
            continue;
        const name = parts[2];
        if (!wholeDisk.test(name))
            continue;
        // fields: reads completed, reads merged, sectors read, ... , sectors written (index 9)
        out.push({
            name: name,
            readSectors: toNum(parts[5]),
            writeSectors: toNum(parts[9])
        });
    }
    return out;
}

// All block devices, including partitions and mapped/RAID devices. Returns
// [{name, readSectors, writeSectors}] so a mounted filesystem can be matched
// to its own /proc/diskstats counters without aggregating unrelated devices.
function parseBlockDiskstats(text) {
    const out = [];
    if (!text)
        return out;
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
        const parts = lines[i].trim().split(/\s+/);
        if (parts.length < 10)
            continue;
        out.push({
            name: parts[2],
            readSectors: toNum(parts[5]),
            writeSectors: toNum(parts[9])
        });
    }
    return out;
}

// ---- lsblk -----------------------------------------------------------------

// Decode the escaped values emitted by `lsblk -P`, including escaped
// newlines in MOUNTPOINTS. Unknown keys are intentionally ignored so newer
// util-linux fields do not break the collector.
function decodeLsblkValue(value) {
    return value
        .replace(/\\x([0-9a-fA-F]{2})/g, function (_, hex) {
            return String.fromCharCode(parseInt(hex, 16));
        })
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, "\\");
}

// `lsblk -bP -o PATH,LABEL,FSTYPE,FSAVAIL,FSSIZE,FSUSED,MOUNTPOINTS,RM,TYPE,TRAN,PKNAME,KNAME`
// -> mounted filesystem rows with byte-accurate capacity information.
// lsblk can repeat a device below a RAID tree, so PATH is deduplicated here.
function parseLsblk(text) {
    const out = [];
    const seen = {};
    if (!text)
        return out;

    const rawRows = [];
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
        const row = {};
        const re = /([A-Z0-9_]+)="((?:\\.|[^"])*)"/g;
        let match;
        while ((match = re.exec(lines[i])) !== null)
            row[match[1]] = decodeLsblkValue(match[2]);
        if (row.PATH)
            rawRows.push(row);
    }

    const byPath = {};
    for (let i = 0; i < rawRows.length; i++)
        byPath[rawRows[i].PATH] = rawRows[i];

    for (let i = 0; i < rawRows.length; i++) {
        const row = rawRows[i];

        const path = row.PATH || "";
        const fsType = row.FSTYPE || "";
        const mountPoints = (row.MOUNTPOINTS || "")
            .split("\n")
            .map(function (p) { return p.trim(); })
            .filter(function (p) { return p && p !== "[SWAP]"; });

        // Free space is a filesystem property; unmounted disks and swap areas
        // are not part of this widget's free-space device list.
        if (!path || path.indexOf("/dev/") !== 0 || !fsType || fsType === "swap" || mountPoints.length === 0)
            continue;
        if (seen[path])
            continue;

        // Root is the useful representative when a Btrfs filesystem has
        // several system subvolume mountpoints (/var/cache, /var/log, ...).
        mountPoints.sort(function (a, b) { return a.length - b.length; });
        const mountPoint = mountPoints[0];
        // EFI/boot partitions are implementation details, not Dolphin-style
        // user storage entries.
        if (mountPoint === "/boot" || mountPoint.indexOf("/boot/") === 0)
            continue;

        // A partition often has an empty TRAN field (notably USB enclosures),
        // so follow PKNAME through the complete block-device chain.
        let cursor = row;
        let transport = "";
        let removable = false;
        for (let depth = 0; cursor && depth < 16; depth++) {
            if (!transport && cursor.TRAN)
                transport = cursor.TRAN.toLowerCase();
            if (cursor.RM === "1")
                removable = true;
            cursor = cursor.PKNAME ? byPath["/dev/" + cursor.PKNAME] : null;
        }
        removable = removable || transport === "usb" || transport === "mmc" || transport === "firewire";
        const hasStats = row.FSSIZE !== undefined && row.FSSIZE !== "";
        seen[path] = true;
        out.push({
            path: path,
            blockName: row.KNAME || path.split("/").pop(),
            label: row.LABEL || "",
            fsType: fsType,
            availableBytes: hasStats && row.FSAVAIL !== "" ? toNum(row.FSAVAIL) : -1,
            sizeBytes: hasStats ? toNum(row.FSSIZE) : -1,
            usedBytes: hasStats && row.FSUSED !== "" ? toNum(row.FSUSED) : -1,
            mountPoint: mountPoint,
            mountPoints: mountPoints,
            isRemovable: removable,
            transport: transport,
            type: row.TYPE || ""
        });
    }
    return out;
}

// ---- /proc/stat ------------------------------------------------------------

// First "cpu " line -> array of jiffies [user, nice, system, idle, iowait, ...]
function parseCpu(text) {
    if (!text)
        return [];
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].indexOf("cpu ") === 0) {
            const parts = lines[i].trim().split(/\s+/).slice(1);
            return parts.map(toNum);
        }
    }
    return [];
}

// Average of per-core "cpu MHz" from /proc/cpuinfo.
function parseCpuMHz(text) {
    if (!text)
        return 0;
    const lines = text.split("\n");
    let sum = 0;
    let count = 0;
    for (let i = 0; i < lines.length; i++) {
        const m = lines[i].match(/cpu MHz\s*:\s*([0-9.]+)/);
        if (!m)
            continue;
        const v = toNum(m[1]);
        if (v > 0) {
            sum += v;
            count++;
        }
    }
    return count > 0 ? sum / count : 0;
}

// ---- /proc/pressure --------------------------------------------------------

// "some avg10=13.59 ..." -> 13.59 (percent)
function parsePressureSome(text) {
    if (!text)
        return -1;
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
        if (lines[i].indexOf("some ") === 0) {
            const m = lines[i].match(/avg10=([0-9.]+)/);
            return m ? toNum(m[1]) : -1;
        }
    }
    return -1;
}

// ---- hwmon / temperatures --------------------------------------------------

// CPU package sensors we accept (AMD/Intel). Skip nvme/gpu/acpi junk.
function isCpuHwmonName(name) {
    return /^(k10temp|coretemp|zenpower|cpu_thermal)$/.test(name || "");
}

// sysfs temp*_input millidegree C -> Celsius. Missing/zero -> NaN.
function parseTempMilli(text) {
    const milli = toNum((text || "").trim());
    return milli > 0 ? milli / 1000 : NaN;
}

// ---- nvidia-smi ------------------------------------------------------------

// "11213, 12288" or "11213, 12288, 48" -> [usedMiB, totalMiB, tempC]
// tempC is NaN when the temperature field is absent.
function parseNvidiaGpu(text) {
    if (!text)
        return [0, 0, NaN];
    const parts = text.trim().split(",");
    const temp = parts.length >= 3 && String(parts[2]).trim() !== ""
        ? toNum(parts[2])
        : NaN;
    return [toNum(parts[0]), toNum(parts[1]), temp];
}

// CSV lines "pid, used_memory, /full/path process args" ->
// [{pid, mib, name, rawName}]
function parseNvidiaApps(text) {
    const out = [];
    if (!text)
        return out;
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line)
            continue;
        const parts = line.split(",");
        if (parts.length < 3)
            continue;
        const pid = toNum(parts[0]);
        const mib = toNum(parts[1]);
        if (pid <= 0 || mib <= 0)
            continue;
        // process_name may contain commas? nvidia-smi quotes never; take rest
        // of the line, strip args, basename.
        let rawName = parts.slice(2).join(",").trim();
        const exe = rawName.split(/\s+/)[0];
        const base = exe.split("/").pop();
        out.push({ pid: pid, mib: mib, name: base || rawName, rawName: rawName });
    }
    return out;
}
