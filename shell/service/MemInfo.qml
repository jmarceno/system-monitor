pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse
import "../lib/Format.js" as Format

// /proc/meminfo + /proc/pressure/memory collector.
// Read-only, async, timer-driven (procfs does not fire inotify reliably).
Singleton {
    id: root

    property real totalKB: 0
    property real availableKB: 0
    property real cacheKB: 0          // Cached + SReclaimable - Shmem
    property real buffersKB: 0
    property real swapCachedKB: 0
    property real swapTotalKB: 0
    property real swapFreeKB: 0
    property real zswapKB: 0
    property real zswappedKB: 0
    // PSI memory pressure "some" avg10, percent. -1 = unavailable.
    property real pressurePct: -1

    readonly property real usedKB: Math.max(0, totalKB - availableKB)
    readonly property real usedPct: totalKB > 0 ? 100 * usedKB / totalKB : 0
    readonly property bool ready: totalKB > 0

    function _parseMeminfo(text) {
        const m = Parse.keyValueMap(text);
        if (!m.MemTotal)
            return;
        root.totalKB = m.MemTotal;
        root.availableKB = m.MemAvailable !== undefined ? m.MemAvailable : (m.MemFree || 0);
        root.cacheKB = Math.max(0, (m.Cached || 0) + (m.SReclaimable || 0) - (m.Shmem || 0));
        root.buffersKB = m.Buffers || 0;
        root.swapCachedKB = m.SwapCached || 0;
        root.swapTotalKB = m.SwapTotal || 0;
        root.swapFreeKB = m.SwapFree || 0;
        root.zswapKB = m.Zswap || 0;
        root.zswappedKB = m.Zswapped || 0;
    }

    FileView {
        id: meminfoView
        path: "/proc/meminfo"
        watchChanges: false
        printErrors: false
        onTextChanged: root._parseMeminfo(text())
    }

    FileView {
        id: pressureView
        path: "/proc/pressure/memory"
        watchChanges: false
        printErrors: false
        onTextChanged: {
            const v = Parse.parsePressureSome(text());
            root.pressurePct = v;
        }
    }

    Timer {
        interval: Config.meminfoIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            meminfoView.reload();
            pressureView.reload();
        }
    }
}
