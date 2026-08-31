import QtQuick
import ".."
import "../lib/Format.js" as Format
import "../service"

// zram card: sizes, compression ratio, zswap + writeback status chips.
Card {
    id: root

    icon: "▣"
    title: Zram.exists ? Zram.device : "zram"

    headerExtras: Row {
        spacing: 8

        Chip {
            label: "zswap"
            value: Zram.zswapStatus
            valueColor: Zram.zswapStatus === "Off" ? Theme.accentGreen : Theme.accentAmber
        }
        Chip {
            label: "writeback"
            value: Zram.writebackStatus
            valueColor: Zram.writebackStatus === "none" ? Theme.accentGreen : Theme.accentAmber
        }
    }

    Text {
        visible: !Zram.exists
        text: "no zram configured"
        color: Theme.textFaint
        font.pixelSize: Theme.fontSizeSm
    }

    Row {
        visible: Zram.exists
        width: parent.width
        spacing: 0

        StatCol { label: "orig"; value: Zram.ready ? Format.fmtBytes(Zram.origBytes) : "…" }
        VDivider {}
        StatCol { label: "compr"; value: Zram.ready ? Format.fmtBytes(Zram.comprBytes) : "…" }
        VDivider {}
        StatCol { label: "mem used"; value: Zram.ready ? Format.fmtBytes(Zram.memUsedBytes) : "…" }
        VDivider {}
        StatCol {
            label: "ratio"
            value: Zram.ratio > 0 ? Zram.ratio.toFixed(1) + "x" : "…"
            valueColor: Zram.ratio >= 2.5 ? Theme.accentGreen : Theme.accentAmber
        }
    }

    Row {
        // Only warn when huge pages exceed 10% of stored data — stray
        // incompressible pages are normal; a flood means the pool is filling
        // with data zram cannot actually shrink.
        visible: Zram.exists && Zram.origBytes > 0 && Zram.hugePages * 4096 > 0.1 * Zram.origBytes
        spacing: 6

        Text {
            text: "⚠"
            color: Theme.accentAmber
            font.pixelSize: Theme.fontSizeSm
        }
        Text {
            text: "huge pages: " + Zram.hugePages.toLocaleString() + " (compression degrading)"
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
        }
    }

    component StatCol: Column {
        id: sc
        property string label: ""
        property string value: ""
        property color valueColor: Theme.text

        width: (parent.width - 3 * parent.spacing) / 4 + 12

        Text {
            text: sc.label
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
        }
        Text {
            text: sc.value
            color: sc.valueColor
            font.pixelSize: Theme.fontSizeMd + 1
            font.bold: true
        }
    }

    component VDivider: Rectangle {
        width: 1
        height: 28
        color: Theme.cardBorder
        anchors.verticalCenter: parent.verticalCenter
    }

    component Chip: Rectangle {
        id: chip
        property string label: ""
        property string value: ""
        property color valueColor: Theme.text

        width: chipRow.implicitWidth + 16
        height: 30
        radius: 8
        color: Theme.track
        border.width: 1
        border.color: Theme.cardBorder

        Row {
            id: chipRow
            anchors.centerIn: parent
            spacing: 5

            Text {
                text: chip.label
                color: Theme.textFaint
                font.pixelSize: Theme.fontSizeSm
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: chip.value
                color: chip.valueColor
                font.pixelSize: Theme.fontSizeSm
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
