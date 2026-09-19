pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick

// AI-spend collector. The UI only renders the snapshot; all credential
// discovery and HTTP live in shell/lib/ai-spend-collect.py (read-only).
//
// Poll is slow on purpose (minutes, not seconds): these are billing APIs,
// not /proc. Missing keys or endpoints render n/a — never retry-storm.
Singleton {
    id: root

    property var providers: []
    property int okCount: 0
    property string generatedAt: ""
    property bool ready: false
    property bool queryFailed: false
    property string failNote: ""

    property string _output: ""

    readonly property bool running: !SystemSnapshot.compactMode

    readonly property var command: [
        "python3", "-u", Quickshell.shellPath("lib/ai-spend-collect.py")
    ]

    function _parse(text) {
        let snap;
        try {
            snap = JSON.parse(text);
        } catch (e) {
            root._fail("snapshot parse failed");
            return;
        }
        const list = snap && Array.isArray(snap.providers) ? snap.providers : [];
        root.providers = list;
        root.okCount = Number.isFinite(snap.okCount) ? snap.okCount : 0;
        root.generatedAt = typeof snap.generatedAt === "string" ? snap.generatedAt : "";
        root.ready = true;
        root.queryFailed = false;
        root.failNote = "";
    }

    function _fail(note) {
        root.ready = false;
        root.queryFailed = true;
        root.failNote = note || "unavailable";
        root.providers = [];
        root.okCount = 0;
        console.warn("system-monitor: ai-spend query failed;", root.failNote);
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
                root._fail("collector exit " + exitCode);
        }
    }

    Timer {
        interval: root.running ? Config.aiSpendIntervalMs : Config.aiSpendCollapsedIntervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            if (!query.running)
                query.exec(root.command);
        }
    }
}
