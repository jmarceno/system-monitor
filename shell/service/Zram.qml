pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse
import "../lib/Format.js" as Format

// zram collector.
// Sources (all read-only, world-readable on this system):
//   /sys/block/<dev>/mm_stat  - sizes in bytes (field count varies 6..9)
//   /sys/block/<dev>/stat     - diskstat layout, for I/O deltas
//   /proc/swaps               - authoritative swap-side usage
//   /sys/module/zswap/parameters/enabled   - zswap status chip
//   /sys/block/<dev>/backing_dev           - writeback status chip
Singleton {
    id: root

    property bool exists: false
    property string device: ""
    property real origBytes: 0          // logical data stored
    property real comprBytes: 0         // compressed size
    property real memUsedBytes: 0       // actual RAM consumed holding zram
    property real hugePages: 0          // ratio-degradation signal
    property real zramSwapUsedKB: 0     // from /proc/swaps
    property real zramSwapSizeKB: 0
    property string zswapStatus: "n/a"  // "On" / "Off" / "n/a"
    property string writebackStatus: "n/a"

    readonly property real ratio: comprBytes > 0 ? origBytes / comprBytes : 0
    readonly property real ramSavedBytes: Math.max(0, origBytes - memUsedBytes)
    readonly property bool ready: exists && memUsedBytes > 0

    // Cumulative I/O counters for swap attribution (SwapDisk reads these).
    // zram writes/reads are page-sized (4 KiB); SwapDisk uses the DELTAS.
    property real _readsCompleted: 0
    property real _writesCompleted: 0
    readonly property real readsCompleted: _readsCompleted
    readonly property real writesCompleted: _writesCompleted

    function _parseMmStat(text) {
        const f = Parse.parseMmStat(text);
        if (f.length < 3) {
            root.exists = false;
            return;
        }
        root.exists = true;
        root.device = Config.zramDevices[0];
        root.origBytes = f[0];
        root.comprBytes = f[1];
        root.memUsedBytes = f[2];
        root.hugePages = f.length > 6 ? f[6] : 0;
    }

    function _parseStat(text) {
        const f = Parse.parseDiskstat(text);
        if (f.length < 6)
            return;
        root._readsCompleted = f[0];
        root._writesCompleted = f[3];
    }

    function _parseSwaps(text) {
        const areas = Parse.parseSwaps(text);
        for (let i = 0; i < areas.length; i++) {
            if (areas[i].isZram) {
                root.zramSwapSizeKB = areas[i].sizeKB;
                root.zramSwapUsedKB = areas[i].usedKB;
                return;
            }
        }
        root.zramSwapSizeKB = 0;
        root.zramSwapUsedKB = 0;
    }

    FileView {
        id: mmStatView
        path: "/sys/block/" + Config.zramDevices[0] + "/mm_stat"
        watchChanges: false
        printErrors: false
        onTextChanged: root._parseMmStat(text())
        onLoadFailed: root.exists = false
    }

    FileView {
        id: statView
        path: "/sys/block/" + Config.zramDevices[0] + "/stat"
        watchChanges: false
        printErrors: false
        onTextChanged: root._parseStat(text())
    }

    FileView {
        id: swapsView
        path: "/proc/swaps"
        watchChanges: false
        printErrors: false
        onTextChanged: root._parseSwaps(text())
    }

    FileView {
        id: zswapView
        path: "/sys/module/zswap/parameters/enabled"
        watchChanges: false
        printErrors: false
        onTextChanged: root.zswapStatus = text().trim() === "Y" ? "On" : "Off"
        onLoadFailed: root.zswapStatus = "n/a"
    }

    FileView {
        id: backingDevView
        path: "/sys/block/" + Config.zramDevices[0] + "/backing_dev"
        watchChanges: false
        printErrors: false
        onTextChanged: root.writebackStatus = text().trim() === "none" ? "none" : text.trim()
        onLoadFailed: root.writebackStatus = "n/a"
    }

    Timer {
        interval: Config.swapIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            mmStatView.reload();
            statView.reload();
            swapsView.reload();
        }
    }

    Timer {
        interval: Config.staticIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            zswapView.reload();
            backingDevView.reload();
        }
    }
}
