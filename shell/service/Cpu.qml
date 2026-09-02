pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse
import "../lib/Format.js" as Format

// CPU busy% (from /proc/stat jiffies), current average core frequency
// (from /proc/cpuinfo "cpu MHz"), and package temperature via hwmon
// (k10temp / coretemp / zenpower / cpu_thermal → temp1_input, °C).
Singleton {
    id: root

    property real busyPct: 0        // 0..100, since last sample
    property real mhz: 0            // average per-core current frequency
    property real tempC: NaN        // package °C; NaN when unavailable
    readonly property bool ready: _prev !== null && mhz > 0

    property var _prev: null
    property int _hwmonProbe: 0
    property bool _hwmonResolved: false

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

    // Avoid chaining reload() inside onLoaded — FileView drops in-flight ops.
    function _scheduleProbe() {
        if (root._hwmonResolved || root._hwmonProbe > 15)
            return;
        probeDefer.restart();
    }

    function _runProbe() {
        if (root._hwmonResolved || root._hwmonProbe > 15)
            return;
        hwmonNameView.path = "/sys/class/hwmon/hwmon" + root._hwmonProbe + "/name";
        hwmonNameView.reload();
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

    // Walk hwmonN/name one index at a time (deferred) until a CPU chip matches.
    FileView {
        id: hwmonNameView
        watchChanges: false
        printErrors: false
        onLoaded: {
            if (root._hwmonResolved)
                return;
            const name = text().trim();
            if (Parse.isCpuHwmonName(name)) {
                root._hwmonResolved = true;
                tempView.path = "/sys/class/hwmon/hwmon" + root._hwmonProbe + "/temp1_input";
                tempDefer.restart();
                return;
            }
            root._hwmonProbe++;
            root._scheduleProbe();
        }
        onLoadFailed: {
            if (root._hwmonResolved)
                return;
            root._hwmonProbe++;
            root._scheduleProbe();
        }
    }

    FileView {
        id: tempView
        watchChanges: false
        printErrors: false
        onTextChanged: root.tempC = Parse.parseTempMilli(text())
        onLoadFailed: root.tempC = NaN
    }

    Timer {
        id: probeDefer
        interval: 0
        repeat: false
        onTriggered: root._runProbe()
    }

    Timer {
        id: tempDefer
        interval: 0
        repeat: false
        onTriggered: tempView.reload()
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
        onTriggered: {
            cpuinfoView.reload();
            if (root._hwmonResolved)
                tempView.reload();
        }
    }

    Component.onCompleted: root._scheduleProbe()
}
