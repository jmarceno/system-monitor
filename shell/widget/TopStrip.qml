import QtQuick
import ".."
import "../lib/Format.js" as Format
import "../service"

// Top summary strip: CPU / RAM / Swap / GPU VRAM ring gauges + disk I/O.
Rectangle {
    id: root

    implicitHeight: strip.implicitHeight + 16
    radius: 12
    color: Theme.cardBg
    border.width: 1
    border.color: Theme.cardBorder

    Row {
        id: strip
        anchors.centerIn: parent
        spacing: 14

        RingGauge {
            label: "CPU"
            value: Cpu.busyPct
            ringColor: Theme.accentCyan
            sub: Format.fmtMHz(Cpu.mhz)
        }

        VDivider {}

        RingGauge {
            label: "RAM"
            value: MemInfo.usedPct
            ringColor: Theme.accentBlue
            sub: MemInfo.ready ? Format.fmtKB(MemInfo.usedKB) + " / " + Format.fmtKB(MemInfo.totalKB) : "…"
        }

        VDivider {}

        RingGauge {
            label: "Swap"
            value: SwapDisk.usedPct
            ringColor: SwapDisk.verdict === 3 ? Theme.accentRed : Theme.accentCyan
            sub: SwapDisk.totalSizeKB > 0 ? Format.fmtKB(SwapDisk.totalUsedKB) + " / " + Format.fmtKB(SwapDisk.totalSizeKB) : "…"
        }

        VDivider {}

        RingGauge {
            label: "GPU VRAM"
            value: Vram.usedPct
            ringColor: Theme.accentAmber
            sub: Vram.available ? Format.fmtKB(Vram.gpuUsedMiB * 1024) + " / " + Format.fmtKB(Vram.gpuTotalMiB * 1024) : "n/a"
        }

        VDivider {}

        // Disk I/O block (mockup): sparkline + R/W rates.
        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Row {
                spacing: 6
                Text {
                    text: "I/O"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeSm
                    anchors.verticalCenter: parent.verticalCenter
                }
                Sparkline {
                    history: DiskIo.history
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            Text {
                text: "R  " + Format.fmtRateKBps(DiskIo.readKBps)
                color: Theme.text
                font.pixelSize: Theme.fontSizeSm
            }
            Text {
                text: "W  " + Format.fmtRateKBps(DiskIo.writeKBps)
                color: Theme.text
                font.pixelSize: Theme.fontSizeSm
            }
        }
    }

    component VDivider: Rectangle {
        width: 1
        height: 36
        color: Theme.cardBorder
        anchors.verticalCenter: parent.verticalCenter
    }
}
