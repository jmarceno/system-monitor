pragma Singleton
import ".."
import Quickshell
import Quickshell.Io
import QtQuick
import "../lib/Parse.js" as Parse

// Per-volume physical I/O collector for the storage sidecar.
//
// /proc/diskstats exposes cumulative 512-byte sector counters for every block
// device. KNAME from the lsblk snapshot is the stable bridge between a mounted
// filesystem and its matching kernel record, including partitions, RAID and
// device-mapper volumes. We intentionally do not sum parent and child devices.
Singleton {
    id: root

    property var samples: []
    property var _previous: null
    property int generation: 0
    readonly property int historyMax: 40
    readonly property bool ready: _previous !== null

    function _keyFor(volume) {
        if (!volume)
            return "";
        if (volume.blockName)
            return volume.blockName;
        const path = String(volume.path || "");
        const parts = path.split("/");
        return parts.length > 0 ? parts[parts.length - 1] : "";
    }

    function _sampleForKey(key) {
        for (let i = 0; i < root.samples.length; i++) {
            if (root.samples[i].blockName === key)
                return root.samples[i];
        }
        return null;
    }

    function _emptySample() {
        return {
            blockName: "",
            readKBps: 0,
            writeKBps: 0,
            totalKBps: 0,
            history: []
        };
    }

    // Called by a delegate binding; StorageIo.generation is read explicitly in
    // the delegate so a new snapshot replaces the sparkline history object.
    function sampleFor(volume) {
        const key = _keyFor(volume);
        if (!key)
            return _emptySample();
        return _sampleForKey(key) || _emptySample();
    }

    function _parse(text) {
        const records = Parse.parseBlockDiskstats(text);
        const current = {};
        for (let i = 0; i < records.length; i++) {
            const record = records[i];
            current[record.name] = {
                readSectors: record.readSectors,
                writeSectors: record.writeSectors
            };
        }

        const previous = root._previous;
        const seconds = Config.diskIoIntervalMs / 1000;
        const next = [];
        for (let i = 0; i < Storage.volumes.length; i++) {
            const volume = Storage.volumes[i];
            const blockName = _keyFor(volume);
            const now = current[blockName];
            const before = previous ? previous[blockName] : null;
            let readKBps = 0;
            let writeKBps = 0;

            if (now && before && seconds > 0) {
                // /proc/diskstats sectors are 512 bytes: 0.5 kB per sector.
                readKBps = Math.max(0, 0.5 * (now.readSectors - before.readSectors) / seconds);
                writeKBps = Math.max(0, 0.5 * (now.writeSectors - before.writeSectors) / seconds);
            }

            const old = _sampleForKey(blockName);
            let history = old ? old.history.slice(-(root.historyMax - 1)) : [];
            if (now && before)
                history.push(readKBps + writeKBps);
            else if (!now)
                history = [];

            next.push({
                blockName: blockName,
                readKBps: readKBps,
                writeKBps: writeKBps,
                totalKBps: readKBps + writeKBps,
                history: history
            });
        }

        root.samples = next;
        root._previous = current;
        root.generation++;
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
