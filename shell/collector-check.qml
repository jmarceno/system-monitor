import QtQuick
import Quickshell
import "service"
import "lib/Format.js" as Format

// Headless verification harness (no windows). Runs the collectors for a few
// seconds, prints their state, and quits. Run:
//   quickshell -p shell/collector-check.qml
ShellRoot {
    // Force early instantiation of the singletons (same as the real UI does
    // via its bindings); otherwise they are created lazily on first access.
    Item {
        property real a: MemInfo.totalKB
        property real b: Cpu.busyPct
        property bool c: Zram.exists
        property var d: SwapDisk.areas
        property var e: StorageIo.samples
        property var f: Vram.procs
        property var g: Storage.volumes
        property var h: AiSpend.providers
    }

    Timer {
        interval: 12000
        running: true
        repeat: false
        onTriggered: {
            const f = Format;
            console.log("=== MemInfo ===");
            console.log("used:", f.fmtKB(MemInfo.usedKB), "/", f.fmtKB(MemInfo.totalKB),
                "(" + f.fmtPct(MemInfo.usedPct) + ")",
                "avail:", f.fmtKB(MemInfo.availableKB),
                "cache:", f.fmtKB(MemInfo.cacheKB),
                "buffers:", f.fmtKB(MemInfo.buffersKB),
                "pressure:", MemInfo.pressurePct);

            console.log("=== Cpu ===");
            console.log("busy:", f.fmtPct(Cpu.busyPct), "mhz:", f.fmtMHz(Cpu.mhz));

            console.log("=== Zram ===");
            console.log("exists:", Zram.exists, Zram.device,
                "orig:", f.fmtBytes(Zram.origBytes),
                "compr:", f.fmtBytes(Zram.comprBytes),
                "memUsed:", f.fmtBytes(Zram.memUsedBytes),
                "ratio:", Zram.ratio.toFixed(2) + "x",
                "swapUsed:", f.fmtKB(Zram.zramSwapUsedKB), "/", f.fmtKB(Zram.zramSwapSizeKB),
                "zswap:", Zram.zswapStatus, "writeback:", Zram.writebackStatus,
                "wPages:", Zram.writesCompleted);

            console.log("=== SwapDisk ===");
            console.log("areas:", JSON.stringify(SwapDisk.areas));
            console.log("zram:", f.fmtKB(SwapDisk.zramUsedKB), "/", f.fmtKB(SwapDisk.zramSizeKB),
                "disk:", f.fmtKB(SwapDisk.diskUsedKB), "/", f.fmtKB(SwapDisk.diskSizeKB));
            console.log("rates: zramOut", f.fmtRateKBps(SwapDisk.zramSwapOutKBps),
                "diskOut", f.fmtRateKBps(SwapDisk.diskSwapOutKBps),
                "zramIn", f.fmtRateKBps(SwapDisk.zramSwapInKBps),
                "diskIn", f.fmtRateKBps(SwapDisk.diskSwapInKBps));
            console.log("verdict:", SwapDisk.verdictText);

            console.log("=== StorageIo ===");
            console.log("samples:", JSON.stringify(StorageIo.samples));

            console.log("=== Vram ===");
            console.log("avail:", Vram.available, f.fmtKB(Vram.gpuUsedMiB * 1024), "/", f.fmtKB(Vram.gpuTotalMiB * 1024), "(" + f.fmtPct(Vram.usedPct) + ")");
            console.log("gpus:", JSON.stringify(Vram.gpus));
            console.log("temps:", JSON.stringify(Vram.temps));
            console.log("procs:", JSON.stringify(Vram.procs));

            console.log("=== Storage ===");
            console.log("ready:", Storage.ready, "volumes:", JSON.stringify(Storage.volumes));

            console.log("=== AiSpend ===");
            console.log("ready:", AiSpend.ready, "ok:", AiSpend.okCount, "failed:", AiSpend.queryFailed);
            console.log("providers:", JSON.stringify(AiSpend.providers));

            console.log("=== ALL CHECKS DONE ===");
            Qt.quit();
        }
    }
}
