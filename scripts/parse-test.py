#!/usr/bin/env python3
"""Parser verification against live system files. Run: python3 scripts/parse-test.py"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sysmon import parse  # noqa: E402

failures = 0


def check(name: str, cond: bool, detail: object = "") -> None:
    global failures
    if cond:
        print(f"  ok  {name}")
    else:
        failures += 1
        print(f"FAIL  {name} {detail}", file=sys.stderr)


def main() -> int:
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    mem = parse.key_value_map(meminfo)
    check("meminfo MemTotal > 0", mem["MemTotal"] > 0, f"got {mem.get('MemTotal')}")
    check("meminfo MemAvailable > 0", mem["MemAvailable"] > 0)

    pressure = Path("/proc/pressure/memory").read_text(encoding="utf-8")
    p = parse.parse_pressure_some(pressure)
    check("pressure some avg10 >= 0", p >= 0, f"got {p}")

    swaps = Path("/proc/swaps").read_text(encoding="utf-8")
    areas = parse.parse_swaps(swaps)
    check("swaps >= 1 area", len(areas) >= 1, f"got {len(areas)}")
    zram_area = next((area for area in areas if area["isZram"]), None)
    disk_area = next((area for area in areas if not area["isZram"]), None)
    check("zram area found", zram_area is not None)
    check(
        "priorities parsed",
        bool(zram_area and isinstance(zram_area["priority"], (int, float))),
        f"{zram_area and zram_area['priority']}/{disk_area and disk_area['priority']} ({disk_area and disk_area['name']})",
    )
    if disk_area:
        check("disk swap size parsed", disk_area["sizeKB"] > 0, disk_area)

    vm = parse.pair_map(Path("/proc/vmstat").read_text(encoding="utf-8"))
    check("pswpin present", "pswpin" in vm and vm["pswpin"] >= 0, f"got {vm.get('pswpin')}")
    check("pswpout present", "pswpout" in vm and vm["pswpout"] >= 0, f"got {vm.get('pswpout')}")

    mm = parse.parse_mm_stat(Path("/sys/block/zram0/mm_stat").read_text(encoding="utf-8"))
    check("mm_stat >= 6 fields", len(mm) >= 6, f"got {len(mm)}")
    check("mm_stat orig > compr > 0", mm[0] > 0 and mm[0] > mm[1] and mm[1] > 0)

    zs = parse.parse_diskstat(Path("/sys/block/zram0/stat").read_text(encoding="utf-8"))
    check("zram stat writes field", len(zs) >= 6 and zs[3] >= 0, f"got {zs[3]}")

    ds = parse.parse_diskstats(Path("/proc/diskstats").read_text(encoding="utf-8"))
    check("diskstats found whole disks", len(ds) > 0, f"got {len(ds)}")
    check(
        "no partitions/zram in diskstats",
        all(parse._WHOLE_DISK.match(item["name"]) for item in ds),
        [item["name"] for item in ds],
    )

    block_ds = parse.parse_block_diskstats(Path("/proc/diskstats").read_text(encoding="utf-8"))
    check("block diskstats includes partitions", any(item["name"][-1].isdigit() for item in block_ds), block_ds[:5])
    synthetic_block = parse.parse_block_diskstats("8 1 sdd1 10 0 2048 0 20 0 4096 0 0 0\n")
    check(
        "block diskstats reads sector counters",
        synthetic_block[0]["readSectors"] == 2048 and synthetic_block[0]["writeSectors"] == 4096,
        synthetic_block,
    )

    synthetic_lsblk = (
        'PATH="/dev/sdd1" LABEL="Expansion" FSTYPE="ext4" '
        'FSAVAIL="853378957312" FSSIZE="1967845998592" FSUSED="1014430375936" '
        'MOUNTPOINTS="/mnt/expansion" RM="0" TYPE="part" TRAN="" PKNAME="sdd" KNAME="sdd1"\n'
        'PATH="/dev/sdd" LABEL="" FSTYPE="" FSAVAIL="" FSSIZE="" FSUSED="" '
        'MOUNTPOINTS="" RM="0" TYPE="disk" TRAN="usb" PKNAME="" KNAME="sdd"\n'
        'PATH="/dev/nvme0n1p1" LABEL="" FSTYPE="btrfs" FSAVAIL="10" '
        'FSSIZE="100" FSUSED="90" MOUNTPOINTS="/var/log\\x0a/" RM="0" TYPE="part" TRAN="nvme" PKNAME="nvme0n1" KNAME="nvme0n1p1"\n'
    )
    synthetic_volumes = parse.parse_lsblk(synthetic_lsblk)
    check("lsblk parses mounted volumes", len(synthetic_volumes) == 2, synthetic_volumes)
    check("lsblk decodes mountpoint escapes", synthetic_volumes[1]["mountPoint"] == "/", synthetic_volumes[1])
    check("lsblk recognizes USB removable transport", synthetic_volumes[0]["isRemovable"] is True)
    check("lsblk keeps byte-accurate free space", synthetic_volumes[0]["availableBytes"] == 853378957312)
    check("lsblk keeps kernel block name", synthetic_volumes[0]["blockName"] == "sdd1", synthetic_volumes[0])

    live_lsblk = subprocess.check_output(
        ["lsblk", "-bP", "-o", "PATH,LABEL,FSTYPE,FSAVAIL,FSSIZE,FSUSED,MOUNTPOINTS,RM,TYPE,TRAN,PKNAME,KNAME"],
        text=True,
    )
    live_volumes = parse.parse_lsblk(live_lsblk)
    check("live lsblk finds mounted storage", len(live_volumes) > 0, f"got {len(live_volumes)}")
    check("live lsblk exposes free bytes", any(volume["availableBytes"] >= 0 for volume in live_volumes), live_volumes)
    expansion = [volume for volume in live_volumes if volume.get("label") == "Expansion"]
    if expansion:
        check("live lsblk inherits USB transport", expansion[0]["isRemovable"] is True, expansion[0])
    else:
        check("live lsblk USB path optional", True)

    cpu = parse.parse_cpu(Path("/proc/stat").read_text(encoding="utf-8"))
    check("cpu jiffies >= 5 fields", len(cpu) >= 5)
    total = sum(cpu)
    check("cpu total > idle", total > cpu[3])

    mhz = parse.parse_cpu_mhz(Path("/proc/cpuinfo").read_text(encoding="utf-8"))
    check("cpu MHz > 0", mhz > 0, f"got {mhz}")

    check("cpu hwmon name k10temp", parse.is_cpu_hwmon_name("k10temp"))
    check("cpu hwmon rejects nvme", not parse.is_cpu_hwmon_name("nvme"))
    check("temp milli → °C", parse.parse_temp_milli("50500") == 50.5, f"got {parse.parse_temp_milli('50500')}")
    check("temp milli empty → NaN", __import__("math").isnan(parse.parse_temp_milli("")))

    used, total_mib, *_ = parse.parse_nvidia_gpu("11213, 12288")
    check("nvidia gpu query", used == 11213 and total_mib == 12288)
    used_t, total_t, temp_c = parse.parse_nvidia_gpu("11213, 12288, 48")
    check("nvidia gpu temp °C", used_t == 11213 and total_t == 12288 and temp_c == 48, f"got {temp_c}")

    gpus = parse.parse_nvidia_gpus(
        "112, 12288, 38, 0, NVIDIA GeForce RTX 3060\n"
        "705, 12288, 45, 1, NVIDIA GeForce RTX 3060\n"
    )
    check("nvidia gpus count", len(gpus) == 2, f"got {len(gpus)}")
    check(
        "nvidia gpu 0",
        bool(gpus and gpus[0]["index"] == 0 and gpus[0]["usedMiB"] == 112 and gpus[0]["totalMiB"] == 12288),
        gpus[0] if gpus else None,
    )
    check(
        "nvidia gpu 1",
        bool(len(gpus) > 1 and gpus[1]["index"] == 1 and gpus[1]["usedMiB"] == 705 and gpus[1]["tempC"] == 45),
        gpus[1] if len(gpus) > 1 else None,
    )
    check("nvidia gpu short name", gpus[0]["shortName"] == "RTX 3060", gpus[0]["shortName"] if gpus else None)
    one_gpu = parse.parse_nvidia_gpus("11213, 12288, 48")
    check(
        "nvidia gpus legacy line",
        len(one_gpu) == 1 and one_gpu[0]["index"] == 0 and one_gpu[0]["usedMiB"] == 11213,
        one_gpu[0] if one_gpu else None,
    )
    check("nvidia gpus empty", parse.parse_nvidia_gpus("") == [])

    apps = parse.parse_nvidia_apps(
        "1163, 25, /usr/bin/kwin_wayland\n"
        "37034, 4516, /opt/opencode_beta.appimage\n"
        "37883, 3564, /usr/local/bin/llama-cli --some args\n"
    )
    check("nvidia apps count", len(apps) == 3, f"got {len(apps)}")
    check(
        "nvidia app basename",
        apps[0]["name"] == "kwin_wayland" and apps[1]["name"] == "opencode_beta.appimage",
        [item["name"] for item in apps],
    )
    check("nvidia app args stripped", apps[2]["name"] == "llama-cli", apps[2]["name"])

    collect_py = ROOT / "sysmon" / "lib" / "ai_spend_collect.py"
    ai_spend = subprocess.check_output(["python3", str(collect_py), "--self-test"], text=True)
    check("ai-spend self-test", "All ai-spend parser checks passed." in ai_spend, ai_spend)

    if failures:
        print(f"\n{failures} check(s) FAILED", file=sys.stderr)
        return 1
    print("\nAll parser checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
