pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse
import "../lib/Format.js" as Format

// Physical disk I/O throughput (added to scope by mock/mockup.png).
// /proc/diskstats deltas, whole disks only (no partitions/zram/loop/dm) to
// avoid double counting. Swapfile traffic is real disk I/O and is included.
Singleton {
    id: root

    property real readKBps: 0
    property real writeKBps: 0
    readonly property real totalKBps: readKBps + writeKBps
    readonly property bool ready: _prev !== null

    // rolling history of total KB/s for the sparkline (bounded, tiny)
    property var history: []
    readonly property int historyMax: 40

    property var _prev: null   // { r, w }

    function _parse(text) {
        const devs = Parse.parseDiskstats(text);
        let r = 0, w = 0;
        for (let i = 0; i < devs.length; i++) {
            r += devs[i].readSectors;
            w += devs[i].writeSectors;
        }
        if (root._prev && Config.diskIoIntervalMs > 0) {
            const sec = Config.diskIoIntervalMs / 1000;
            // sectors are 512 bytes
            root.readKBps = Math.max(0, 0.5 * (r - root._prev.r) / sec);
            root.writeKBps = Math.max(0, 0.5 * (w - root._prev.w) / sec);
            const h = root.history.slice(-(root.historyMax - 1));
            h.push(root.readKBps + root.writeKBps);
            root.history = h;
        }
        root._prev = { r: r, w: w };
    }

    FileView {
        id: diskstatsView
        path: "/proc/diskstats"
        watchChanges: false
        printErrors: false
        onTextChanged: root._parse(text())
    }

    Timer {
        interval: Config.diskIoIntervalMs
        running: !SystemSnapshot.compactMode
        repeat: true
        triggeredOnStart: true
        onTriggered: diskstatsView.reload()
    }
}
