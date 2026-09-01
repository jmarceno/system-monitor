pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse

// Mounted storage collector for the device sidecar.
//
// `lsblk -bP` is a read-only util-linux query over the kernel's block-device
// and filesystem metadata. It is deliberately preferred over a hardcoded
// mount list: labels, free bytes, hot-plugged USB media and removals all flow
// into the next snapshot automatically.
Singleton {
    id: root

    property var volumes: []
    // [{kind: "section", label: ...}, {kind: "volume", volume: ...}]
    property var rows: []
    property bool ready: false
    property bool _queryFailed: false
    property string _output: ""

    readonly property bool queryFailed: _queryFailed
    readonly property var command: [
        "lsblk", "-bP", "-o",
        "PATH,LABEL,FSTYPE,FSAVAIL,FSSIZE,FSUSED,MOUNTPOINTS,RM,TYPE,TRAN,PKNAME,KNAME"
    ]

    function _fallbackName(volume) {
        if (volume.mountPoint === "/" || volume.mountPoint === "/home")
            return "Internal drive";
        const bits = volume.mountPoint.split("/").filter(function (bit) { return bit.length > 0; });
        return bits.length > 0 ? bits[bits.length - 1] : volume.path.split("/").pop();
    }

    function _decorate(parsed) {
        const out = [];
        for (let i = 0; i < parsed.length; i++) {
            const v = parsed[i];
            const size = v.sizeBytes > 0 ? v.sizeBytes : -1;
            const available = v.availableBytes >= 0 ? v.availableBytes : -1;
            out.push({
                path: v.path,
                blockName: v.blockName,
                label: v.label,
                name: v.label || _fallbackName(v),
                fsType: v.fsType,
                sizeBytes: size,
                availableBytes: available,
                usedBytes: v.usedBytes,
                usedPct: size > 0 && v.usedBytes >= 0 ? Math.max(0, Math.min(100, 100 * v.usedBytes / size)) : -1,
                mountPoint: v.mountPoint,
                mountPoints: v.mountPoints,
                isRemovable: v.isRemovable,
                transport: v.transport,
                type: v.type
            });
        }

        out.sort(function (a, b) {
            if (a.isRemovable !== b.isRemovable)
                return a.isRemovable ? 1 : -1;
            return a.name.localeCompare(b.name);
        });
        return out;
    }

    function _makeRows(volumes) {
        const internal = volumes.filter(function (v) { return !v.isRemovable; });
        const removable = volumes.filter(function (v) { return v.isRemovable; });
        const out = [];
        if (internal.length > 0) {
            out.push({ kind: "section", label: "Internal drives" });
            for (let i = 0; i < internal.length; i++)
                out.push({ kind: "volume", volume: internal[i] });
        }
        if (removable.length > 0) {
            out.push({ kind: "section", label: "Removable drives" });
            for (let i = 0; i < removable.length; i++)
                out.push({ kind: "volume", volume: removable[i] });
        }
        return out;
    }

    function _parse(text) {
        const parsed = _decorate(Parse.parseLsblk(text));
        root.volumes = parsed;
        root.rows = _makeRows(parsed);
        root.ready = true;
        root._queryFailed = false;
    }

    function _fail() {
        root.ready = false;
        root._queryFailed = true;
        root.volumes = [];
        root.rows = [];
        console.warn("system-monitor: lsblk query failed; storage sidecar unavailable");
    }

    Process {
        id: query

        stdout: SplitParser {
            onRead: data => root._output += data + "\n"
        }

        onStarted: root._output = ""
        onExited: (exitCode, exitStatus) => {
            const output = root._output;
            root._output = "";
            if (exitCode === 0)
                root._parse(output);
            else
                root._fail();
        }
    }

    Timer {
        interval: Config.storageIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            if (!query.running)
                query.exec(root.command);
        }
    }
}
