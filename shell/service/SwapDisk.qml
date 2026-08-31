pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse
import "../lib/Format.js" as Format

// Swap attribution collector — the flagship feature.
//
// /proc/vmstat pswpin/pswpout count ALL swap I/O including zram; raw rates
// overstate disk activity. We subtract zram's own page counters (read from
// Zram.writesCompleted / readsCompleted, both sampled on the same 2 s cadence)
// to attribute swap I/O to zram (in-RAM compaction) vs real disk swap.
//
// The per-area "used" delta from /proc/swaps is also tracked as the
// authoritative net-balance view, immune to attribution edge cases.
Singleton {
    id: root

    // Areas split by kind: [{name,type,sizeKB,usedKB,priority,isZram,usedDeltaKB}]
    property var areas: []
    property real zramSizeKB: 0
    property real zramUsedKB: 0
    property real diskSizeKB: 0
    property real diskUsedKB: 0

    // Attributed throughput (kB/s), clamped >= 0 against jitter.
    property real diskSwapOutKBps: 0
    property real diskSwapInKBps: 0
    property real zramSwapOutKBps: 0
    property real zramSwapInKBps: 0

    // Verdict: 0 idle, 1 zram-only (healthy), 2 draining, 3 disk pressure
    property int verdict: 0
    readonly property string verdictText: ["idle", "zram-only", "draining", "disk-pressure"][verdict]

    readonly property real totalSizeKB: zramSizeKB + diskSizeKB
    readonly property real totalUsedKB: zramUsedKB + diskUsedKB
    readonly property real usedPct: totalSizeKB > 0 ? 100 * totalUsedKB / totalSizeKB : 0

    property var _prev: null   // { pswpin, pswpout, zramR, zramW, zramUsed, diskUsed }
    readonly property bool hasSample: _prev !== null

    function _sample(text) {
        const vm = Parse.pairMap(text);
        const areas = Parse.parseSwaps(swapsView.text());
        let zramUsed = 0, diskUsed = 0, zramSize = 0, diskSize = 0;
        for (let i = 0; i < areas.length; i++) {
            areas[i].usedDeltaKB = 0;
            if (areas[i].isZram) {
                zramUsed += areas[i].usedKB;
                zramSize += areas[i].sizeKB;
            } else {
                diskUsed += areas[i].usedKB;
                diskSize += areas[i].sizeKB;
            }
        }

        const zramR = Zram.readsCompleted;
        const zramW = Zram.writesCompleted;
        const now = { pswpin: vm.pswpin || 0, pswpout: vm.pswpout || 0, zramR: zramR, zramW: zramW, zramUsed: zramUsed, diskUsed: diskUsed };

        if (root._prev && Config.swapIntervalMs > 0) {
            const sec = Config.swapIntervalMs / 1000;
            const pswpinD = Math.max(0, now.pswpin - root._prev.pswpin);
            const pswpoutD = Math.max(0, now.pswpout - root._prev.pswpout);
            const zramRD = Math.max(0, now.zramR - root._prev.zramR);
            const zramWD = Math.max(0, now.zramW - root._prev.zramW);

            // pages are 4 KiB. zram counters are page counts (4 KiB writes).
            const zramInKBps = 4 * Math.min(zramRD, pswpinD) / sec;
            const zramOutKBps = 4 * Math.min(zramWD, pswpoutD) / sec;
            root.zramSwapInKBps = zramInKBps;
            root.zramSwapOutKBps = zramOutKBps;
            root.diskSwapInKBps = Math.max(0, 4 * (pswpinD - zramRD) / sec);
            root.diskSwapOutKBps = Math.max(0, 4 * (pswpoutD - zramWD) / sec);

            for (let i = 0; i < areas.length; i++) {
                areas[i].usedDeltaKB = areas[i].isZram
                    ? zramUsed - root._prev.zramUsed
                    : _deltaFor(areas, areas[i], root._prev.areas);
            }

            // verdict
            const diskGrow = now.diskUsed - root._prev.diskUsed;
            const zramGrow = now.zramUsed - root._prev.zramUsed;
            if (root.diskSwapOutKBps > Config.diskSwapAlertKBps || diskGrow > 0)
                root.verdict = 3;
            else if (zramGrow > 0)
                root.verdict = 1;
            else if (diskGrow < 0 || zramGrow < 0)
                root.verdict = 2;
            else
                root.verdict = 0;
        }

        now.areas = areas;
        root._prev = now;
        root.areas = areas;
        root.zramUsedKB = zramUsed;
        root.zramSizeKB = zramSize;
        root.diskUsedKB = diskUsed;
        root.diskSizeKB = diskSize;
    }

    // per-area delta matched by name across samples (multiple swap files)
    function _deltaFor(current, area, prevAreas) {
        if (!prevAreas)
            return 0;
        for (let i = 0; i < prevAreas.length; i++) {
            if (prevAreas[i].name === area.name)
                return area.usedKB - prevAreas[i].usedKB;
        }
        return 0;
    }

    FileView {
        id: swapsView
        path: "/proc/swaps"
        watchChanges: false
        printErrors: false
    }

    FileView {
        id: vmstatView
        path: "/proc/vmstat"
        watchChanges: false
        printErrors: false
    }

    Timer {
        interval: Config.swapIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            swapsView.reload();
            vmstatView.reload();
            // reload() is async; _sample runs after both views refresh.
            Qt.callLater(root._sample, vmstatView.text());
        }
    }
}
