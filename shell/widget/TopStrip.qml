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
        anchors.fill: parent
        anchors.margins: 8
        spacing: 4

        readonly property real cellWidth: (width - spacing * 4) / 5

        RingGauge {
            width: strip.cellWidth
            label: "CPU"
            value: Cpu.busyPct
            ringColor: Theme.accentCyan
            sub: Format.fmtMHz(Cpu.mhz)
        }

        RingGauge {
            width: strip.cellWidth
            label: "RAM"
            value: MemInfo.usedPct
            ringColor: Theme.accentBlue
            sub: MemInfo.ready ? Format.fmtKB(MemInfo.usedKB) + " / " + Format.fmtKB(MemInfo.totalKB) : "…"
        }

        RingGauge {
            width: strip.cellWidth
            label: "Swap"
            value: SwapDisk.usedPct
            ringColor: SwapDisk.verdict === 3 ? Theme.accentRed : Theme.accentCyan
            sub: SwapDisk.totalSizeKB > 0 ? Format.fmtKB(SwapDisk.totalUsedKB) + " / " + Format.fmtKB(SwapDisk.totalSizeKB) : "…"
        }

        RingGauge {
            width: strip.cellWidth
            label: "GPU VRAM"
            value: Vram.usedPct
            ringColor: Theme.accentAmber
            sub: Vram.available ? Format.fmtKB(Vram.gpuUsedMiB * 1024) + " / " + Format.fmtKB(Vram.gpuTotalMiB * 1024) : "n/a"
        }

        // Disk I/O block (mockup): sparkline + R/W rates.
        Column {
            id: ioBlock
            width: strip.cellWidth
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Row {
                width: parent.width
                spacing: 6
                Text {
                    id: ioLabel
                    text: "I/O"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeSm
                    anchors.verticalCenter: parent.verticalCenter
                }
                Sparkline {
                    width: Math.max(24, ioBlock.width - ioLabel.implicitWidth - 6)
                    history: DiskIo.history
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            Text {
                width: parent.width
                text: "R  " + Format.fmtRateKBps(DiskIo.readKBps)
                color: Theme.text
                font.pixelSize: Theme.fontSizeSm
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: "W  " + Format.fmtRateKBps(DiskIo.writeKBps)
                color: Theme.text
                font.pixelSize: Theme.fontSizeSm
                elide: Text.ElideRight
            }
        }
    }
}
