import QtQuick
import ".."
import "../lib/Format.js" as Format
import "../service"

// NVIDIA VRAM card: total usage + top consumers (read-only nvidia-smi).
Card {
    id: root

    icon: "◉"
    title: "NVIDIA VRAM"
    iconColor: Theme.accentGreen

    headerExtras: Row {
        spacing: 6
        Text {
            text: Vram.available
                ? Format.fmtKB(Vram.gpuUsedMiB * 1024) + " / " + Format.fmtKB(Vram.gpuTotalMiB * 1024) : "n/a"
            color: Theme.text
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: Vram.available ? "  (" + Format.fmtPct(Vram.usedPct) + ")" : ""
            color: Theme.textFaint
            font.pixelSize: Theme.fontSizeSm
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Text {
        visible: !Vram.available
        text: Vram.nvidiaFailed ? "nvidia-smi unavailable — VRAM card disabled" : "querying nvidia-smi…"
        color: Theme.textFaint
        font.pixelSize: Theme.fontSizeSm
    }

    Bar {
        visible: Vram.available
        value: Vram.usedPct
        fillColor: Theme.accentAmber
    }

    Text {
        visible: Vram.available
        text: "Top processes by VRAM (nvidia-smi)"
        color: Theme.textMuted
        font.pixelSize: Theme.fontSizeSm
    }

    Column {
        visible: Vram.available && Vram.procs.length > 0
        width: parent.width
        spacing: 4

        Repeater {
            model: Vram.procs

            delegate: Item {
                id: procRow
                required property var modelData
                width: parent.width
                height: 16

                readonly property real maxMib: Vram.procs.length > 0 ? Math.max(Vram.procs[0].mib, 1) : 1

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Rectangle {
                        width: 7
                        height: 7
                        radius: 4
                        color: Theme.accentAmber
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: procRow.modelData.name
                        color: Theme.text
                        font.pixelSize: Theme.fontSizeSm
                        anchors.verticalCenter: parent.verticalCenter
                        width: 110
                        elide: Text.ElideRight
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.leftMargin: 123
                    anchors.right: parent.right
                    anchors.rightMargin: 110
                    anchors.verticalCenter: parent.verticalCenter
                    height: 8
                    radius: 4
                    color: Theme.track

                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: Math.max(4, parent.width * Format.clamp(procRow.modelData.mib / procRow.maxMib, 0, 1))
                        radius: parent.radius
                        color: Theme.accentAmber
                    }
                }

                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 58
                    anchors.verticalCenter: parent.verticalCenter
                    text: Format.fmtKB(procRow.modelData.mib * 1024)
                    color: Theme.text
                    font.pixelSize: Theme.fontSizeSm
                    font.bold: true
                }
                Text {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: Vram.gpuTotalMiB > 0 ? Math.round(100 * procRow.modelData.mib / Vram.gpuTotalMiB) + "%" : ""
                    color: Theme.textFaint
                    font.pixelSize: Theme.fontSizeSm
                }
            }
        }
    }

    Text {
        visible: Vram.available && Vram.procs.length === 0
        text: "no VRAM consumers reported"
        color: Theme.textFaint
        font.pixelSize: Theme.fontSizeSm
    }
}
