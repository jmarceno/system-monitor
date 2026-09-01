import QtQuick
import ".."
import "../service"
import "../lib/Format.js" as Format

// Expandable device sidecar. Its height is supplied by MonitorWindow so the
// panel always tracks the full height of the main System Monitor card.
Rectangle {
    id: root

    property bool expanded: false
    signal toggleRequested()
    readonly property int contentMargin: 8

    implicitWidth: expanded ? Config.storageExpandedWidth : Config.storageCollapsedWidth
    implicitHeight: 1
    width: implicitWidth
    radius: 12
    color: Theme.cardBg
    border.width: 1
    border.color: Theme.cardBorder
    clip: true

    Behavior on width {
        NumberAnimation {
            duration: 220
            easing.type: Easing.OutCubic
        }
    }

    Column {
        id: content
        anchors.fill: parent
        anchors.margins: root.contentMargin
        spacing: 8

        Item {
            id: header
            width: parent.width
            height: 32

            Text {
                visible: root.expanded
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                text: "Storage"
                color: Theme.text
                font.pixelSize: Theme.fontSizeLg
                font.bold: true
            }

            Text {
                visible: root.expanded && Storage.ready
                anchors.right: toggle.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: Storage.volumes.length
                color: Theme.textFaint
                font.pixelSize: Theme.fontSizeSm
            }

            Rectangle {
                id: toggle
                width: 32
                height: 32
                x: root.expanded ? parent.width - width : (parent.width - width) / 2
                radius: 8
                color: toggleMouse.containsMouse ? Theme.track : "transparent"
                border.width: 1
                border.color: root.expanded ? Theme.cardBorder : Theme.accentCyan

                Text {
                    anchors.centerIn: parent
                    text: root.expanded ? "›" : "‹"
                    color: Theme.accentCyan
                    font.pixelSize: 20
                    font.bold: true
                }

                MouseArea {
                    id: toggleMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.toggleRequested()
                }
            }
        }

        ListView {
            id: deviceList
            visible: root.expanded && Storage.ready && Storage.rows.length > 0
            width: parent.width
            height: Math.max(0, root.height - header.height - content.spacing - root.contentMargin * 2)
            clip: true
            spacing: 4
            model: Storage.rows

            delegate: Item {
                id: row
                required property var modelData
                width: deviceList.width
                property int ioGeneration: StorageIo.generation
                property var ioSnapshot: {
                    const tick = ioGeneration;
                    return StorageIo.sampleFor(modelData.kind === "volume" ? modelData.volume : null);
                }
                height: modelData.kind === "section" ? 18 : 88

                Text {
                    visible: row.modelData.kind === "section"
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.modelData.kind === "section" ? row.modelData.label : ""
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSizeSm
                    font.bold: true
                }

                Rectangle {
                    visible: row.modelData.kind === "volume"
                    anchors.fill: parent
                    radius: 8
                    color: Theme.windowBg
                    border.width: 1
                    border.color: Theme.cardBorder

                    Column {
                        anchors.fill: parent
                        anchors.margins: 4
                        spacing: 1

                        Row {
                            width: parent.width
                            spacing: 5

                            Text {
                                width: parent.width - kindText.implicitWidth - parent.spacing
                                text: row.modelData.kind === "volume" ? row.modelData.volume.name : ""
                                color: Theme.text
                                font.pixelSize: Theme.fontSizeMd
                                font.bold: true
                                elide: Text.ElideRight
                            }

                            Text {
                                id: kindText
                                text: row.modelData.kind === "volume" && row.modelData.volume.isRemovable ? "USB" : ""
                                color: Theme.accentAmber
                                font.pixelSize: Theme.fontSizeSm
                                font.bold: true
                            }
                        }

                        Text {
                            width: parent.width
                            text: {
                                if (row.modelData.kind !== "volume")
                                    return "";
                                const v = row.modelData.volume;
                                return v.availableBytes >= 0 && v.sizeBytes > 0
                                    ? Format.fmtBytes(v.availableBytes) + " free / " + Format.fmtBytes(v.sizeBytes)
                                    : "free space unavailable";
                            }
                            color: Theme.text
                            font.pixelSize: Theme.fontSizeSm
                            elide: Text.ElideRight
                        }

                        Bar {
                            width: parent.width
                            height: 6
                            value: row.modelData.kind === "volume" ? row.modelData.volume.usedPct : 0
                            fillColor: row.modelData.kind === "volume" && row.modelData.volume.isRemovable
                                ? Theme.accentAmber : Theme.accentBlue
                        }

                        Text {
                            width: parent.width
                            text: row.modelData.kind === "volume" ? row.modelData.volume.mountPoint : ""
                            color: Theme.textFaint
                            font.pixelSize: Theme.fontSizeSm
                            elide: Text.ElideMiddle
                        }

                        Row {
                            width: parent.width
                            spacing: 5

                            Text {
                                id: ioLabel
                                text: "I/O"
                                color: Theme.text
                                font.pixelSize: Theme.fontSizeSm
                                font.bold: true
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Item {
                                width: Math.max(0, parent.width - ioLabel.implicitWidth - ioRead.implicitWidth - ioWrite.implicitWidth - parent.spacing * 3)
                                height: 1
                            }

                            Text {
                                id: ioRead
                                text: "R  " + Format.fmtRateKBps(row.ioSnapshot.readKBps)
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSizeSm
                                anchors.verticalCenter: parent.verticalCenter
                            }

                            Text {
                                id: ioWrite
                                text: "W  " + Format.fmtRateKBps(row.ioSnapshot.writeKBps)
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSizeSm
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        Sparkline {
                            width: parent.width
                            height: 18
                            history: row.ioSnapshot.history
                            lineColor: row.modelData.kind === "volume" && row.modelData.volume.isRemovable
                                ? Theme.accentAmber : Theme.accentCyan
                        }
                    }
                }
            }
        }

        Text {
            visible: root.expanded && !Storage.ready
            width: parent.width
            wrapMode: Text.Wrap
            text: Storage.queryFailed ? "Storage query unavailable" : "Reading mounted devices…"
            color: Theme.textFaint
            font.pixelSize: Theme.fontSizeSm
        }

        Text {
            visible: root.expanded && Storage.ready && Storage.rows.length === 0
            width: parent.width
            wrapMode: Text.Wrap
            text: "No mounted storage devices"
            color: Theme.textFaint
            font.pixelSize: Theme.fontSizeSm
        }
    }
}
