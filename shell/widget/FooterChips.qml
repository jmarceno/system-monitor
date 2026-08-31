import QtQuick
import ".."

// Footer chips mirroring the safety posture from the mockup.
Rectangle {
    id: root

    implicitHeight: flow.implicitHeight + 8
    radius: 12
    color: "transparent"

    Flow {
        id: flow
        anchors.fill: parent
        spacing: 8

        Chip { label: "no root" }
        Chip { label: "async I/O" }
        Chip { label: "bounded polling" }
        Chip { label: "graceful n/a" }
        Chip {
            label: "kill switch"
            value: "systemctl --user stop"
            iconGlyph: "⛨"
        }
    }

    component Chip: Rectangle {
        id: chip
        property string label: ""
        property string value: ""
        property string iconGlyph: "✓"

        width: row.implicitWidth + 18
        height: 30
        radius: 8
        color: Theme.cardBg
        border.width: 1
        border.color: Theme.cardBorder

        Row {
            id: row
            anchors.centerIn: parent
            spacing: 6

            Text {
                text: chip.iconGlyph === "✓" ? "✓" : chip.iconGlyph
                color: chip.iconGlyph === "✓" ? Theme.accentGreen : Theme.accentCyan
                font.pixelSize: Theme.fontSizeMd
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: chip.label
                color: Theme.text
                font.pixelSize: Theme.fontSizeSm
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: chip.value
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSm
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
