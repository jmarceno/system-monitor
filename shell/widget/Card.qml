import QtQuick
import ".."

// Base card container matching the mockup: rounded dark card, optional
// highlight border (used by the Swap Attribution card), header with icon
// chip, title, right-aligned extras slot, and a content column.
Rectangle {
    id: root

    default property alias content: body.data
    property alias title: titleText.text
    property alias icon: iconText.text
    property color iconColor: Theme.accentCyan
    property bool highlight: false
    property alias headerExtras: headerExtrasRow.data

    implicitHeight: col.implicitHeight + 20
    radius: 12
    color: highlight ? Theme.cardHighlightBg : Theme.cardBg
    border.width: highlight ? 2 : 1
    border.color: highlight ? Theme.cardHighlightBorder : Theme.cardBorder

    Column {
        id: col
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        Item {
            width: parent.width
            height: 26

            Row {
                id: leftGroup
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8

                Rectangle {
                    width: 26
                    height: 26
                    radius: 7
                    color: Qt.rgba(root.iconColor.r, root.iconColor.g, root.iconColor.b, 0.13)
                    border.color: root.iconColor
                    border.width: 1

                    Text {
                        id: iconText
                        anchors.centerIn: parent
                        text: root.icon
                        color: root.iconColor
                        font.pixelSize: 13
                        font.bold: true
                    }
                }

                Text {
                    id: titleText
                    anchors.verticalCenter: parent.verticalCenter
                    color: Theme.text
                    font.bold: true
                    font.pixelSize: Theme.fontSizeXl
                }
            }

            Row {
                id: headerExtrasRow
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
            }
        }

        Column {
            id: body
            width: parent.width
            spacing: 6
        }
    }
}
