"""Pure parsing helpers for /proc, /sys, lsblk, nvidia-smi, and amdgpu fdinfo."""

from __future__ import annotations

import math
import re
from typing import Any


def to_num(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def key_value_map(text: str | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not text:
        return out
    for line in text.split("\n"):
        idx = line.find(":")
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1 :].strip().split()
        out[key] = to_num(val[0] if val else "")
    return out


def pair_map(text: str | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if not text:
        return out
    for line in text.split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2:
            out[parts[0]] = to_num(parts[1])
    return out


def parse_swaps(text: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not text:
        return out
    lines = text.split("\n")
    for line in lines[1:]:
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        out.append({
            "name": parts[0],
            "type": parts[1],
            "sizeKB": to_num(parts[2]),
            "usedKB": to_num(parts[3]),
            "priority": to_num(parts[4]),
            "isZram": parts[0].startswith("/dev/zram"),
        })
    return out


def parse_mm_stat(text: str | None) -> list[float]:
    if not text:
        return []
    return [to_num(part) for part in text.strip().split()]


def parse_diskstat(text: str | None) -> list[float]:
    if not text:
        return []
    return [to_num(part) for part in text.strip().split()]


_WHOLE_DISK = re.compile(r"^(nvme\d+n\d+|sd[a-z]+|vd[a-z]+|hd[a-z]+|mmcblk\d+|sr\d+)$")


def parse_diskstats(text: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not text:
        return out
    for line in text.split("\n"):
        parts = line.strip().split()
        if len(parts) < 10:
            continue
        name = parts[2]
        if not _WHOLE_DISK.match(name):
            continue
        out.append({
            "name": name,
            "readSectors": to_num(parts[5]),
            "writeSectors": to_num(parts[9]),
        })
    return out


def parse_block_diskstats(text: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not text:
        return out
    for line in text.split("\n"):
        parts = line.strip().split()
        if len(parts) < 10:
            continue
        out.append({
            "name": parts[2],
            "readSectors": to_num(parts[5]),
            "writeSectors": to_num(parts[9]),
        })
    return out


_LSBLK_HEX = re.compile(r"\\x([0-9a-fA-F]{2})")
_LSBLK_FIELD = re.compile(r'([A-Z0-9_]+)="((?:\\.|[^"])*)"')


def decode_lsblk_value(value: str) -> str:
    decoded = _LSBLK_HEX.sub(lambda match: chr(int(match.group(1), 16)), value)
    return decoded.replace('\\"', '"').replace("\\\\", "\\")


def parse_lsblk(text: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: dict[str, bool] = {}
    if not text:
        return out

    raw_rows: list[dict[str, str]] = []
    for line in text.split("\n"):
        row = {
            key: decode_lsblk_value(value)
            for key, value in _LSBLK_FIELD.findall(line)
        }
        if row.get("PATH"):
            raw_rows.append(row)

    by_path = {row["PATH"]: row for row in raw_rows}

    for row in raw_rows:
        path = row.get("PATH") or ""
        fs_type = row.get("FSTYPE") or ""
        mount_points = [
            point.strip()
            for point in (row.get("MOUNTPOINTS") or "").split("\n")
            if point.strip() and point.strip() != "[SWAP]"
        ]
        if (
            not path
            or not path.startswith("/dev/")
            or not fs_type
            or fs_type == "swap"
            or not mount_points
        ):
            continue
        if seen.get(path):
            continue

        mount_points.sort(key=len)
        mount_point = mount_points[0]
        if mount_point == "/boot" or mount_point.startswith("/boot/"):
            continue

        cursor: dict[str, str] | None = row
        transport = ""
        removable = False
        for _ in range(16):
            if cursor is None:
                break
            if not transport and cursor.get("TRAN"):
                transport = cursor["TRAN"].lower()
            if cursor.get("RM") == "1":
                removable = True
            pkname = cursor.get("PKNAME")
            cursor = by_path.get("/dev/" + pkname) if pkname else None
        removable = removable or transport in ("usb", "mmc", "firewire")
        has_stats = row.get("FSSIZE") is not None and row.get("FSSIZE") != ""
        seen[path] = True
        out.append({
            "path": path,
            "blockName": row.get("KNAME") or path.split("/")[-1],
            "label": row.get("LABEL") or "",
            "fsType": fs_type,
            "availableBytes": to_num(row["FSAVAIL"]) if has_stats and row.get("FSAVAIL") != "" else -1,
            "sizeBytes": to_num(row["FSSIZE"]) if has_stats else -1,
            "usedBytes": to_num(row["FSUSED"]) if has_stats and row.get("FSUSED") != "" else -1,
            "mountPoint": mount_point,
            "mountPoints": mount_points,
            "isRemovable": removable,
            "transport": transport,
            "type": row.get("TYPE") or "",
        })
    return out


def parse_cpu(text: str | None) -> list[float]:
    if not text:
        return []
    for line in text.split("\n"):
        if line.startswith("cpu "):
            return [to_num(part) for part in line.strip().split()[1:]]
    return []


def parse_cpu_mhz(text: str | None) -> float:
    if not text:
        return 0.0
    total = 0.0
    count = 0
    for line in text.split("\n"):
        match = re.search(r"cpu MHz\s*:\s*([0-9.]+)", line)
        if not match:
            continue
        value = to_num(match.group(1))
        if value > 0:
            total += value
            count += 1
    return total / count if count else 0.0


def parse_pressure_some(text: str | None) -> float:
    if not text:
        return -1.0
    for line in text.split("\n"):
        if line.startswith("some "):
            match = re.search(r"avg10=([0-9.]+)", line)
            return to_num(match.group(1)) if match else -1.0
    return -1.0


def is_cpu_hwmon_name(name: str | None) -> bool:
    return bool(re.match(r"^(k10temp|coretemp|zenpower|cpu_thermal)$", name or ""))


def parse_temp_milli(text: str | None) -> float:
    milli = to_num((text or "").strip())
    return milli / 1000 if milli > 0 else math.nan


def short_gpu_name(name: str | None) -> str:
    cleaned = str(name or "").strip()
    cleaned = re.sub(r"^NVIDIA\s+", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^GeForce\s+", "", cleaned, flags=re.I)
    # pci.ids marketing names look like "Baffin [Radeon RX 550 640SP / RX 560/560X]".
    bracket = re.search(r"\[([^\[\]]+)\]", cleaned)
    if bracket:
        cleaned = bracket.group(1).strip()
    return cleaned.strip()


_DRM_SIZE = re.compile(r"^(\d+)\s*([KMGT]iB|B)?$", re.I)
_DRM_SIZE_SCALE = {
    "b": 1,
    "kib": 1024,
    "mib": 1024 ** 2,
    "gib": 1024 ** 3,
    "tib": 1024 ** 4,
}


def parse_drm_size_bytes(text: str | None) -> float:
    """drm-usage-stats size. A missing unit is bytes; amdgpu prints KiB or MiB."""
    if not text:
        return 0.0
    match = _DRM_SIZE.match(text.strip())
    if not match:
        return 0.0
    scale = _DRM_SIZE_SCALE[(match.group(2) or "B").lower()]
    return to_num(match.group(1)) * scale


def parse_amd_fdinfo(text: str | None) -> dict[str, Any] | None:
    """One `/proc/<pid>/fdinfo/<fd>` blob for an amdgpu client.

    Prefers `drm-resident-vram` (pages actually in VRAM). Older kernels only
    expose `drm-memory-vram`. Returns None when the fd is not amdgpu.
    """
    if not text or "drm-driver:" not in text:
        return None
    fields: dict[str, str] = {}
    for line in text.split("\n"):
        idx = line.find(":")
        if idx < 0:
            continue
        fields[line[:idx].strip()] = line[idx + 1 :].strip()
    if fields.get("drm-driver") != "amdgpu":
        return None
    raw = fields.get("drm-resident-vram")
    if raw is None:
        raw = fields.get("drm-memory-vram")
    return {
        "pdev": fields.get("drm-pdev", ""),
        "client": fields.get("drm-client-id", ""),
        "vramBytes": parse_drm_size_bytes(raw),
    }


def sum_amd_vram_by_pid(samples: list[dict[str, Any]]) -> dict[int, float]:
    """Sum unique amdgpu clients per pid.

    One process often holds several fds for the same `drm-client-id`; those
    must not be added twice. Distinct clients on the same pid are added.
    Shared buffers can still appear in more than one pid — that sum is not
    the GPU total from `mem_info_vram_used`.
    """
    best: dict[tuple[int, str, str], float] = {}
    for sample in samples:
        pid = int(to_num(sample.get("pid")))
        if pid <= 0:
            continue
        key = (pid, str(sample.get("pdev") or ""), str(sample.get("client") or ""))
        amount = to_num(sample.get("vramBytes"))
        best[key] = max(best.get(key, 0.0), amount)
    totals: dict[int, float] = {}
    for (pid, _pdev, _client), amount in best.items():
        if amount <= 0:
            continue
        totals[pid] = totals.get(pid, 0.0) + amount
    return totals


def parse_pci_vendor_devices(text: str | None, vendor_id: str) -> dict[str, str]:
    """Device id → name for one vendor block in pci.ids. Subsystem lines are ignored."""
    want = vendor_id.lower().removeprefix("0x")
    out: dict[str, str] = {}
    if not text or not want:
        return out
    in_vendor = False
    for line in text.split("\n"):
        if not line or line.startswith("#"):
            continue
        if not line.startswith("\t"):
            token = line.split()
            in_vendor = bool(token) and token[0].lower() == want
            continue
        if not in_vendor or line.startswith("\t\t"):
            continue
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            out[parts[0].lower()] = parts[1].strip()
    return out


def parse_nvidia_gpu(text: str | None) -> list[float]:
    if not text:
        return [0.0, 0.0, math.nan]
    parts = text.strip().split(",")
    temp = to_num(parts[2]) if len(parts) >= 3 and parts[2].strip() != "" else math.nan
    return [to_num(parts[0]), to_num(parts[1] if len(parts) > 1 else 0), temp]


def parse_nvidia_gpus(text: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not text:
        return out
    for line in str(text).split("\n"):
        line = line.strip()
        if not line:
            continue
        used, total, temp = parse_nvidia_gpu(line)
        if not (total > 0):
            continue
        parts = line.split(",")
        index = to_num(parts[3]) if len(parts) >= 4 and parts[3].strip() != "" else len(out)
        name = ",".join(parts[4:]).strip() if len(parts) >= 5 else ""
        out.append({
            "index": index,
            "name": name,
            "shortName": short_gpu_name(name),
            "usedMiB": used,
            "totalMiB": total,
            "tempC": temp,
        })
    return out


def parse_nvidia_apps(text: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not text:
        return out
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        pid = to_num(parts[0])
        mib = to_num(parts[1])
        if pid <= 0 or mib <= 0:
            continue
        raw_name = ",".join(parts[2:]).strip()
        exe = raw_name.split()[0] if raw_name.split() else raw_name
        base = exe.split("/")[-1]
        out.append({
            "pid": int(pid),
            "mib": mib,
            "name": base or raw_name,
            "rawName": raw_name,
        })
    return out
