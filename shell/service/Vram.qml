pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse
import "../lib/Format.js" as Format

// VRAM collector. Primary path: read-only nvidia-smi queries.
// Per-process entries are validated against /proc/<pid>/comm each tick to
// guard against PID-reuse races (dead pids dropped, never mislabeled).
// Note: comm is capped at 15 chars by the kernel, so matching is prefix-based.
Singleton {
    id: root

    // Combined across every nvidia-smi GPU. The ring gauge uses these.
    property real gpuUsedMiB: 0
    property real gpuTotalMiB: 0
    property real tempC: NaN        // hottest GPU die °C (fallback); the gauge uses gpus[].tempC
    readonly property real usedPct: gpuTotalMiB > 0 ? 100 * gpuUsedMiB / gpuTotalMiB : 0
    readonly property bool available: gpuTotalMiB > 0

    // [{index, name, shortName, usedMiB, totalMiB, tempC, usedPct}] one entry per GPU.
    property var gpus: []
    // One die °C per GPU, same order as gpus. The ring gauge stacks these.
    property var temps: []

    // [{pid, mib, name}] sorted desc by mib, top Config.topProcesses.
    // name is deduped ("llama-cli", "llama-cli #2").
    property var procs: []

    property bool _nvidiaFailed: false
    readonly property bool nvidiaFailed: _nvidiaFailed

    readonly property bool running: !SystemSnapshot.compactMode

    property string _gpuOutput: ""
    property string _appsOutput: ""

    readonly property var gpuCommand: ["nvidia-smi", "--query-gpu=memory.used,memory.total,temperature.gpu,index,name", "--format=csv,noheader,nounits"]
    readonly property var appsCommand: ["nvidia-smi", "--query-compute-apps=pid,used_memory,process_name", "--format=csv,noheader,nounits"]

    function _parseGpu(text) {
        const list = Parse.parseNvidiaGpus(text);
        if (list.length === 0)
            return;
        let used = 0;
        let total = 0;
        let maxTemp = NaN;
        const gpus = [];
        const temps = [];
        for (let i = 0; i < list.length; i++) {
            const g = list[i];
            used += g.usedMiB;
            total += g.totalMiB;
            const t = g.tempC;
            const tempC = isFinite(t) && t > 0 ? t : NaN;
            if (isFinite(tempC) && (!isFinite(maxTemp) || tempC > maxTemp))
                maxTemp = tempC;
            temps.push(tempC);
            gpus.push({
                index: g.index,
                name: g.name,
                shortName: g.shortName,
                usedMiB: g.usedMiB,
                totalMiB: g.totalMiB,
                tempC: tempC,
                usedPct: g.totalMiB > 0 ? 100 * g.usedMiB / g.totalMiB : 0
            });
        }
        root.gpus = gpus;
        root.temps = temps;
        root.gpuUsedMiB = used;
        root.gpuTotalMiB = total;
        root.tempC = maxTemp;
    }

    function _parseApps(text) {
        const list = Parse.parseNvidiaApps(text);
        if (list.length === 0) {
            root.procs = [];
            return;
        }
        _validateAll(list, 0, []);
    }

    // Sequentially validate each entry against /proc/<pid>/comm, then publish.
    function _validateAll(list, index, acc) {
        if (index >= list.length) {
            _publish(acc);
            return;
        }
        const entry = list[index];
        _probeComm(entry.pid, entry.name, function (ok) {
            if (ok)
                acc.push(entry);
            _validateAll(list, index + 1, acc);
        });
    }

    function _publish(entries) {
        entries.sort(function (a, b) { return b.mib - a.mib; });
        const top = entries.slice(0, Config.topProcesses);
        const seen = {};
        for (let i = 0; i < top.length; i++) {
            const n = top[i].name;
            seen[n] = (seen[n] || 0) + 1;
            if (seen[n] > 1)
                top[i].name = n + " #" + seen[n];
        }
        root.procs = top;
    }

    // Read /proc/<pid>/comm and confirm it plausibly matches the basename
    // nvidia-smi reported. cb(ok) is called exactly once.
    function _probeComm(pid, basename, cb) {
        const probe = probeComponent.createObject(null, {
            path: "/proc/" + pid + "/comm",
            callback: function (ok) {
                probe.destroy();
                cb(ok);
            },
            expectedBase: basename
        });        if (!probe)
            cb(false);
    }

    Component {
        id: probeComponent
        FileView {
            property var callback: null
            property string expectedBase: ""
            watchChanges: false
            printErrors: false
            onLoaded: {
                if (!callback)
                    return;
                const comm = text().trim();
                // comm is truncated to 15 chars; accept prefix matches both ways.
                const ok = comm.length > 0 && (expectedBase.indexOf(comm) === 0 || comm.indexOf(expectedBase) === 0);
                const cb = callback;
                callback = null;
                cb(ok);
            }
            onLoadFailed: {
                if (!callback)
                    return;
                const cb = callback;
                callback = null;
                cb(false);
            }
        }
    }

    Process {
        id: gpuProc
        stdout: SplitParser {
            onRead: data => root._gpuOutput += data + "\n"
        }
        onStarted: root._gpuOutput = ""
        onExited: (exitCode, exitStatus) => {
            const output = root._gpuOutput;
            root._gpuOutput = "";
            if (exitCode === 0)
                root._parseGpu(output);
            else
                root._fail();
        }
    }

    Process {
        id: appsProc
        stdout: SplitParser {
            onRead: data => root._appsOutput += data + "\n"
        }
        onStarted: root._appsOutput = ""
        onExited: (exitCode, exitStatus) => {
            const output = root._appsOutput;
            root._appsOutput = "";
            if (exitCode === 0)
                root._parseApps(output);
            else
                root._fail();
        }
    }

    function _fail() {
        if (root._nvidiaFailed)
            return;
        root._nvidiaFailed = true;
        console.warn("system-monitor: nvidia-smi query failed; VRAM card unavailable");
    }

    // GPU totals every tick; the per-process list (2nd subprocess spawn) is
    // polled less often — it is the least volatile data on the card.
    Timer {
        interval: root.running ? Config.vramIntervalMs : Config.vramCollapsedIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: gpuProc.exec(root.gpuCommand)
    }

    Timer {
        interval: root.running ? Config.vramAppsIntervalMs : Config.vramCollapsedIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: appsProc.exec(root.appsCommand)
    }
}
