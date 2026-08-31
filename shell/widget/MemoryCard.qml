import QtQuick
import ".."
import "../lib/Format.js" as Format
import "../service"

// RAM card: usage bar + honest breakdown (cache is reclaimable, not "used").
Card {
    id: root

    icon: "▦"
    title: "Memory"

    headerExtras: Row {
        spacing: 6
        Text {
            text: "RAM"
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: MemInfo.ready ? Format.fmtKB(MemInfo.usedKB) + " / " + Format.fmtKB(MemInfo.totalKB) : "…"
            color: Theme.text
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Bar {
        value: MemInfo.usedPct
        fillColor: Theme.accentBlue
    }

    Row {
        width: parent.width
        spacing: 8

        StatLabel { label: "Cache"; value: MemInfo.ready ? Format.fmtKB(MemInfo.cacheKB) : "…" }
        Dot {}
        StatLabel { label: "Available"; value: MemInfo.ready ? Format.fmtKB(MemInfo.availableKB) : "…" }
        Dot {}
        StatLabel { label: "Buffers"; value: MemInfo.ready ? Format.fmtKB(MemInfo.buffersKB) : "…" }
        Dot {}
        StatLabel {
            label: "Memory pressure"
            value: MemInfo.pressurePct >= 0 ? Format.fmtPct(MemInfo.pressurePct) : "n/a"
            valueColor: MemInfo.pressurePct < 20 ? Theme.accentGreen
                : MemInfo.pressurePct < 50 ? Theme.accentAmber : Theme.accentRed
        }
    }

    component StatLabel: Row {
        id: sl
        property string label: ""
        property string value: ""
        property color valueColor: Theme.text

        Text {
            text: sl.label
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: sl.value
            color: sl.valueColor
            font.pixelSize: Theme.fontSizeSm
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
            leftPadding: 4
        }
    }

    component Dot: Text {
        text: "•"
        color: Theme.textFaint
        font.pixelSize: Theme.fontSizeSm
        anchors.verticalCenter: parent.verticalCenter
    }
}
