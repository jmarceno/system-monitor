import QtQuick
import ".."
import "../lib/Format.js" as Format
import "../service"

// Swap Attribution card — the flagship feature.
// Per-area bars (zram vs disk) plus the attributed disk swap-out rate.
// Highlighted border in the mockup: this card is why the widget exists.
Card {
    id: root

    icon: "⇄"
    title: "Swap Attribution"
    highlight: true
    iconColor: Theme.accentCyan

    Repeater {
        model: SwapDisk.areas

        delegate: Column {
            id: areaRow
            required property var modelData
            width: parent.width
            spacing: 3

            Item {
                width: parent.width
                height: 16

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    Text {
                        text: areaRow.modelData.name
                        color: Theme.text
                        font.pixelSize: Theme.fontSizeMd
                    }
                    Text {
                        text: "•  priority " + areaRow.modelData.priority
                        color: Theme.textFaint
                        font.pixelSize: Theme.fontSizeSm
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6

                    Text {
                        text: Format.fmtKB(areaRow.modelData.usedKB) + " / " + Format.fmtKB(areaRow.modelData.sizeKB)
                        color: Theme.text
                        font.pixelSize: Theme.fontSizeSm
                        font.bold: true
                    }
                    Text {
                        text: areaRow.modelData.sizeKB > 0
                            ? "(" + Math.round(100 * areaRow.modelData.usedKB / areaRow.modelData.sizeKB) + "%)" : ""
                        color: Theme.textFaint
                        font.pixelSize: Theme.fontSizeSm
                    }
                }
            }

            Bar {
                value: areaRow.modelData.sizeKB > 0 ? 100 * areaRow.modelData.usedKB / areaRow.modelData.sizeKB : 0
                fillColor: areaRow.modelData.isZram ? Theme.accentCyan : Theme.accentAmber
            }
        }
    }

    // Verdict line
    Row {
        spacing: 6
        topPadding: 4

        Text {
            text: "ⓘ"
            color: root.rateColor()
            font.pixelSize: Theme.fontSizeMd
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: {
                if (SwapDisk.totalSizeKB <= 0)
                    return "No swap areas detected";
                if (!SwapDisk.hasSample)
                    return "Measuring swap activity…";
                if (SwapDisk.verdict === 3)
                    return "Disk swap write rate: " + Format.fmtRateKBps(SwapDisk.diskSwapOutKBps);
                if (SwapDisk.verdict === 1)
                    return "Compacting in RAM (" + Format.fmtRateKBps(SwapDisk.zramSwapOutKBps) + " through zram)";
                if (SwapDisk.verdict === 2)
                    return "Swap being read back (in: " + Format.fmtRateKBps(SwapDisk.zramSwapInKBps + SwapDisk.diskSwapInKBps) + ")";
                return "Disk swap write rate: 0 MB/s";
            }
            color: root.rateColor()
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Column {
        width: parent.width
        spacing: 1

        Text {
            width: parent.width
            text: "If the disk swap area is not growing, nothing is being written to disk."
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            text: "Raw paging/swapout corrected to avoid counting zram as disk I/O."
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
            wrapMode: Text.WordWrap
        }
    }

    function rateColor() {
        if (SwapDisk.verdict === 3)
            return Theme.accentRed;
        if (SwapDisk.verdict === 2)
            return Theme.accentAmber;
        return Theme.accentCyan;
    }
}
