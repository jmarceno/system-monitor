pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse
import "../lib/Format.js" as Format

// CPU busy% (from /proc/stat jiffies) and current average core frequency
// (from /proc/cpuinfo "cpu MHz"). Added to scope by mock/mockup.png.
Singleton {
    id: root

    property real busyPct: 0        // 0..100, since last sample
    property real mhz: 0            // average per-core current frequency
    readonly property bool ready: _prev !== null && mhz > 0

    property var _prev: null

    function _parseStat(text) {
        const j = Parse.parseCpu(text);
        if (j.length < 5)
            return;
        const total = j.reduce((a, b) => a + b, 0);
        const idle = j[3] + j[4]; // idle + iowait
        if (root._prev) {
            const dTotal = total - root._prev.total;
            const dIdle = idle - root._prev.idle;
            root.busyPct = dTotal > 0 ? Format.clamp(100 * (dTotal - dIdle) / dTotal, 0, 100) : 0;
        }
        root._prev = { total: total, idle: idle };
    }

    FileView {
        id: statView
        path: "/proc/stat"
        watchChanges: false
        printErrors: false
        onTextChanged: root._parseStat(text())
    }

    FileView {
        id: cpuinfoView
        path: "/proc/cpuinfo"
        watchChanges: false
        printErrors: false
        onTextChanged: root.mhz = Parse.parseCpuMHz(text())
    }

    Timer {
        interval: Config.cpuIntervalMs
        running: !SystemSnapshot.compactMode
        repeat: true
        triggeredOnStart: true
        onTriggered: statView.reload()
    }

    Timer {
        interval: Config.cpuinfoIntervalMs
        running: !SystemSnapshot.compactMode
        repeat: true
        triggeredOnStart: true
        onTriggered: cpuinfoView.reload()
    }
}
