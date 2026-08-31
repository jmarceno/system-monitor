pragma Singleton
import ".."
import Quickshell

// Aggregation point: widgets import ONLY this singleton, never /proc or /sys.
Singleton {
    id: root

    // Set by MonitorWindow: true when collapsed to the pill; collectors use
    // it to pause or slow down (bounded polling even when data is stale).
    property bool compactMode: false

    readonly property var mem: MemInfo
    readonly property var cpu: Cpu
    readonly property var zram: Zram
    readonly property var swap: SwapDisk
    readonly property var diskIo: DiskIo
    readonly property var vram: Vram
}
