import QtQuick
import ".."
import "../lib/Format.js" as Format
import "../service"

// Top summary strip: two roomy gauge rows plus a full-width disk I/O row.
Rectangle {
    id: root

    implicitHeight: strip.implicitHeight + 20
    radius: 12
    color: Theme.cardBg
    border.width: 1
    border.color: Theme.cardBorder

    Column {
        id: strip
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10

        // CPU and GPU stay together as compute load; RAM and swap form the
        // second memory-pressure row. Two columns give every gauge enough
        // room for a larger ring and an untruncated value.
        Row {
            width: parent.width
            spacing: 12

            RingGauge {
                width: (parent.width - parent.spacing) / 2
                label: "CPU"
                value: Cpu.busyPct
                ringColor: Theme.accentCyan
                sub: Format.fmtMHz(Cpu.mhz)
            }

            RingGauge {
                width: (parent.width - parent.spacing) / 2
                label: "GPU VRAM"
                value: Vram.usedPct
                ringColor: Theme.accentAmber
                sub: Vram.available ? Format.fmtKB(Vram.gpuUsedMiB * 1024) + " / " + Format.fmtKB(Vram.gpuTotalMiB * 1024) : "n/a"
            }
        }

        Row {
            width: parent.width
            spacing: 12

            RingGauge {
                width: (parent.width - parent.spacing) / 2
                label: "RAM"
                value: MemInfo.usedPct
                ringColor: Theme.accentBlue
                sub: MemInfo.ready ? Format.fmtKB(MemInfo.usedKB) + " / " + Format.fmtKB(MemInfo.totalKB) : "…"
            }

            RingGauge {
                width: (parent.width - parent.spacing) / 2
                label: "Swap"
                value: SwapDisk.usedPct
                ringColor: SwapDisk.verdict === 3 ? Theme.accentRed : Theme.accentCyan
                sub: SwapDisk.totalSizeKB > 0 ? Format.fmtKB(SwapDisk.totalUsedKB) + " / " + Format.fmtKB(SwapDisk.totalSizeKB) : "…"
            }
        }

        // Disk I/O gets the full card width so the chart is readable instead
        // of being squeezed into the fifth gauge cell.
        Column {
            id: ioBlock
            width: parent.width
            spacing: 5

            Row {
                width: parent.width
                spacing: 12

                Text {
                    id: ioTitle
                    text: "I/O"
                    color: Theme.text
                    font.pixelSize: Theme.fontSizeMd
                    font.bold: true
                    anchors.verticalCenter: parent.verticalCenter
                }

                Item { width: Math.max(0, parent.width - ioTitle.implicitWidth - ioRead.implicitWidth - ioWrite.implicitWidth - parent.spacing * 3); height: 1 }

                Text {
                    id: ioRead
                    text: "R  " + Format.fmtRateKBps(DiskIo.readKBps)
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeMd
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    id: ioWrite
                    text: "W  " + Format.fmtRateKBps(DiskIo.writeKBps)
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeMd
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            Sparkline {
                width: parent.width
                height: 40
                history: DiskIo.history
            }
        }
    }
}
