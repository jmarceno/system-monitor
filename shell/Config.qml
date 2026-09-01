pragma Singleton
import Quickshell

// Central user-tunable knobs. Nothing else in the shell may hardcode
// intervals, sizes, thresholds or device names (AGENTS.md rule).
Singleton {
    id: root

    // Poll intervals (ms). Kept modest per the bounded-polling budget.
    property int meminfoIntervalMs: 1000
    property int cpuIntervalMs: 1000
    property int swapIntervalMs: 2000
    property int diskIoIntervalMs: 2000
    property int vramIntervalMs: 5000
    property int vramAppsIntervalMs: 10000 // process list is the least volatile
    property int vramCollapsedIntervalMs: 15000
    property int cpuinfoIntervalMs: 2000
    property int staticIntervalMs: 10000 // zswap/writeback status
    property int storageIntervalMs: 5000 // mounted devices / free space

    // Swap attribution: rate above this (kB/s) is flagged as real disk
    // swap-out pressure. 0 = any nonzero disk swap-out flags.
    property real diskSwapAlertKBps: 0

    // VRAM card: how many top consumers to list.
    property int topProcesses: 5

    // Window geometry (logical px).
    property int windowWidth: 440
    property int collapsedWidth: 300
    property int storageCollapsedWidth: 42
    property int storageExpandedWidth: 254

    // zram devices to track (missing ones render "no zram configured").
    property var zramDevices: ["zram0"]
}
