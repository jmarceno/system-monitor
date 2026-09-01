#!/usr/bin/env node
// Parser verification against live system files. Run: node scripts/parse-test.mjs
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// Parse.js is a QML .pragma library; strip the pragma for node.
const src = readFileSync(new URL("../shell/lib/Parse.js", import.meta.url), "utf8")
    .replace(/^\.pragma library.*$/m, "");
const tmp = mkdtempSync(join(tmpdir(), "sm-parse-"));
const fnNames = [...src.matchAll(/^function (\w+)\(/gm)].map(m => m[1]);
const modPath = join(tmp, "Parse.mjs");
writeFileSync(modPath, src + `\nexport { ${fnNames.join(", ")} };`);
const Parse = await import(pathToFileURL(modPath));

let failures = 0;function check(name, cond, detail = "") {
    if (cond) {
        console.log(`  ok  ${name}`);
    } else {
        failures++;
        console.error(`FAIL  ${name} ${detail}`);
    }
}

// --- meminfo ---
const meminfo = readFileSync("/proc/meminfo", "utf8");
const mem = Parse.keyValueMap(meminfo);
check("meminfo MemTotal > 0", mem.MemTotal > 0, `got ${mem.MemTotal}`);
check("meminfo MemAvailable > 0", mem.MemAvailable > 0);

// --- pressure ---
const pressure = readFileSync("/proc/pressure/memory", "utf8");
const p = Parse.parsePressureSome(pressure);
check("pressure some avg10 >= 0", p >= 0, `got ${p}`);

// --- swaps ---
const swaps = readFileSync("/proc/swaps", "utf8");
const areas = Parse.parseSwaps(swaps);
check("swaps >= 2 areas", areas.length >= 2, `got ${areas.length}`);
const zramArea = areas.find(a => a.isZram);
const diskArea = areas.find(a => !a.isZram);
check("zram area found", !!zramArea);
check("disk swap area found", !!diskArea);
check("zram usedKB > 0", zramArea && zramArea.usedKB > 0);
check("priorities parsed", zramArea.priority === 100 && diskArea.priority === 10,
    `${zramArea.priority}/${diskArea.priority}`);

// --- vmstat ---
const vm = Parse.pairMap(readFileSync("/proc/vmstat", "utf8"));
check("pswpin present", Number.isFinite(vm.pswpin) && vm.pswpin >= 0, `got ${vm.pswpin}`);
check("pswpout present", vm.pswpout > 0);

// --- mm_stat ---
const mm = Parse.parseMmStat(readFileSync("/sys/block/zram0/mm_stat", "utf8"));
check("mm_stat >= 6 fields", mm.length >= 6, `got ${mm.length}`);
check("mm_stat orig > compr > 0", mm[0] > 0 && mm[0] > mm[1] && mm[1] > 0);

// --- zram stat ---
const zs = Parse.parseDiskstat(readFileSync("/sys/block/zram0/stat", "utf8"));
check("zram stat writes field", zs.length >= 6 && zs[3] >= 0, `got ${zs[3]}`);

// --- diskstats ---
const ds = Parse.parseDiskstats(readFileSync("/proc/diskstats", "utf8"));
check("diskstats found whole disks", ds.length > 0, `got ${ds.length}`);
check("no partitions/zram in diskstats",
    ds.every(d => /^(nvme\d+n\d+|sd[a-z]+|vd[a-z]+|hd[a-z]+|mmcblk\d+|sr\d+)$/.test(d.name)),
    JSON.stringify(ds.map(d => d.name)));

// --- lsblk storage ---------------------------------------------------------
const syntheticLsblk = 'PATH="/dev/sdd1" LABEL="Expansion" FSTYPE="ext4" ' +
    'FSAVAIL="853378957312" FSSIZE="1967845998592" FSUSED="1014430375936" ' +
    'MOUNTPOINTS="/mnt/expansion" RM="0" TYPE="part" TRAN="" PKNAME="sdd"\n' +
    'PATH="/dev/sdd" LABEL="" FSTYPE="" FSAVAIL="" FSSIZE="" FSUSED="" ' +
    'MOUNTPOINTS="" RM="0" TYPE="disk" TRAN="usb" PKNAME=""\n' +
    'PATH="/dev/nvme0n1p1" LABEL="" FSTYPE="btrfs" FSAVAIL="10" ' +
    'FSSIZE="100" FSUSED="90" MOUNTPOINTS="/var/log\\x0a/" RM="0" TYPE="part" TRAN="nvme" PKNAME="nvme0n1"\n';
const syntheticVolumes = Parse.parseLsblk(syntheticLsblk);
check("lsblk parses mounted volumes", syntheticVolumes.length === 2, JSON.stringify(syntheticVolumes));
check("lsblk decodes mountpoint escapes", syntheticVolumes[1].mountPoint === "/", JSON.stringify(syntheticVolumes[1]));
check("lsblk recognizes USB removable transport", syntheticVolumes[0].isRemovable === true);
check("lsblk keeps byte-accurate free space", syntheticVolumes[0].availableBytes === 853378957312);

const liveLsblk = execFileSync("lsblk", ["-bP", "-o", "PATH,LABEL,FSTYPE,FSAVAIL,FSSIZE,FSUSED,MOUNTPOINTS,RM,TYPE,TRAN,PKNAME"], { encoding: "utf8" });
const liveVolumes = Parse.parseLsblk(liveLsblk);
check("live lsblk finds mounted storage", liveVolumes.length > 0, `got ${liveVolumes.length}`);
check("live lsblk exposes free bytes", liveVolumes.some(v => v.availableBytes >= 0), JSON.stringify(liveVolumes));
check("live lsblk inherits USB transport", liveVolumes.some(v => v.label === "Expansion" && v.isRemovable), JSON.stringify(liveVolumes));

// --- /proc/stat cpu ---
const cpu = Parse.parseCpu(readFileSync("/proc/stat", "utf8"));
check("cpu jiffies >= 5 fields", cpu.length >= 5);
const total = cpu.reduce((a, b) => a + b, 0);
check("cpu total > idle", total > cpu[3]);

// --- /proc/cpuinfo MHz ---
const mhz = Parse.parseCpuMHz(readFileSync("/proc/cpuinfo", "utf8"));
check("cpu MHz > 0", mhz > 0, `got ${mhz}`);

// --- synthetic nvidia-smi ---
const [used, totalMiB] = Parse.parseNvidiaGpu("11213, 12288");
check("nvidia gpu query", used === 11213 && totalMiB === 12288);

const apps = Parse.parseNvidiaApps(
    "1163, 25, /usr/bin/kwin_wayland\n" +
    "37034, 4516, /opt/opencode_beta.appimage\n" +
    "37883, 3564, /usr/local/bin/llama-cli --some args\n");
check("nvidia apps count", apps.length === 3, `got ${apps.length}`);
check("nvidia app basename", apps[0].name === "kwin_wayland" && apps[1].name === "opencode_beta.appimage",
    JSON.stringify(apps.map(a => a.name)));
check("nvidia app args stripped", apps[2].name === "llama-cli", apps[2].name);

if (failures > 0) {
    console.error(`\n${failures} check(s) FAILED`);
    process.exit(1);
}
console.log("\nAll parser checks passed.");
