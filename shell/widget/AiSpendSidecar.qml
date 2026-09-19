import QtQuick
import ".."
import "../service"

// Expandable AI-spend sidecar, immediately to the right of Storage.
// Height is supplied by MonitorWindow so the panel tracks the main card.
Rectangle {
    id: root

    property bool expanded: false
    signal toggleRequested()
    readonly property int contentMargin: 8

    implicitWidth: expanded ? Config.aiSpendExpandedWidth : Config.aiSpendCollapsedWidth
    implicitHeight: 1
    width: implicitWidth
    radius: 12
    color: Theme.cardBg
    border.width: 1
    border.color: Theme.cardBorder
    clip: true

    function hasPct(pct) {
        return typeof pct === "number" && isFinite(pct);
    }

    function barColor(pct) {
        if (!hasPct(pct))
            return Theme.accentCyan;
        if (pct >= 90)
            return Theme.accentRed;
        if (pct >= 70)
            return Theme.accentAmber;
        return Theme.accentGreen;
    }

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
                text: "AI spend"
                color: Theme.text
                font.pixelSize: Theme.fontSizeLg
                font.bold: true
            }

            Text {
                visible: root.expanded && AiSpend.ready
                anchors.right: toggle.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: AiSpend.okCount
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
                border.color: root.expanded ? Theme.cardBorder : Theme.accentAmber

                Text {
                    anchors.centerIn: parent
                    text: root.expanded ? "›" : "$"
                    color: Theme.accentAmber
                    font.pixelSize: root.expanded ? 20 : 14
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
            id: spendList
            visible: root.expanded && AiSpend.ready && AiSpend.providers.length > 0
            width: parent.width
            height: Math.max(0, root.height - header.height - content.spacing - root.contentMargin * 2)
            clip: true
            spacing: 6
            model: AiSpend.providers

            delegate: Rectangle {
                id: card
                required property var modelData
                width: spendList.width
                implicitHeight: cardCol.implicitHeight + 12
                height: implicitHeight
                radius: 8
                color: Theme.windowBg
                border.width: 1
                border.color: Theme.cardBorder

                Column {
                    id: cardCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 6
                    spacing: 3

                    Row {
                        width: parent.width
                        spacing: 6

                        Text {
                            width: parent.width - badge.implicitWidth - parent.spacing
                            text: card.modelData && card.modelData.name ? card.modelData.name : ""
                            color: Theme.text
                            font.pixelSize: Theme.fontSizeMd
                            font.bold: true
                            elide: Text.ElideRight
                        }

                        Text {
                            id: badge
                            visible: !!(card.modelData && card.modelData.unofficial)
                            text: "unoff."
                            color: Theme.accentAmber
                            font.pixelSize: Theme.fontSizeSm
                            font.bold: true
                        }
                    }

                    Row {
                        width: parent.width
                        spacing: 6

                        Text {
                            text: card.modelData && card.modelData.headline ? card.modelData.headline : "n/a"
                            color: card.modelData && card.modelData.status === "ok"
                                ? root.barColor(card.modelData.pct)
                                : Theme.textMuted
                            font.pixelSize: Theme.fontSizeLg
                            font.bold: true
                        }

                        Text {
                            visible: !!(card.modelData && card.modelData.headlineLabel)
                            anchors.verticalCenter: parent.verticalCenter
                            text: card.modelData && card.modelData.headlineLabel ? card.modelData.headlineLabel : ""
                            color: Theme.textFaint
                            font.pixelSize: Theme.fontSizeSm
                        }
                    }

                    Bar {
                        visible: card.modelData && root.hasPct(card.modelData.pct)
                            && !(card.modelData.meters && card.modelData.meters.length > 0)
                        width: parent.width
                        height: 6
                        value: card.modelData && root.hasPct(card.modelData.pct) ? card.modelData.pct : 0
                        fillColor: root.barColor(card.modelData ? card.modelData.pct : NaN)
                    }

                    Repeater {
                        model: card.modelData && card.modelData.meters ? card.modelData.meters : []

                        Column {
                            id: meterCol
                            required property var modelData
                            width: cardCol.width
                            spacing: 1

                            Row {
                                width: parent.width
                                spacing: 6

                                Text {
                                    width: Math.max(0, parent.width - meterPct.implicitWidth - parent.spacing)
                                    text: meterCol.modelData && meterCol.modelData.label ? meterCol.modelData.label : ""
                                    color: Theme.textFaint
                                    font.pixelSize: Theme.fontSizeSm
                                    elide: Text.ElideRight
                                }

                                Text {
                                    id: meterPct
                                    text: meterCol.modelData && root.hasPct(meterCol.modelData.pct)
                                        ? Math.round(meterCol.modelData.pct) + "%"
                                        : "n/a"
                                    color: Theme.text
                                    font.pixelSize: Theme.fontSizeSm
                                    font.bold: true
                                }
                            }

                            Bar {
                                width: parent.width
                                height: 6
                                value: meterCol.modelData && root.hasPct(meterCol.modelData.pct)
                                    ? meterCol.modelData.pct : 0
                                fillColor: root.barColor(meterCol.modelData ? meterCol.modelData.pct : NaN)
                            }
                        }
                    }

                    Text {
                        visible: !!(card.modelData && card.modelData.detail)
                        width: parent.width
                        wrapMode: Text.Wrap
                        text: card.modelData && card.modelData.detail ? card.modelData.detail : ""
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSizeSm
                    }

                    Repeater {
                        model: card.modelData && card.modelData.lines ? card.modelData.lines : []

                        Row {
                            id: lineRow
                            required property var modelData
                            width: cardCol.width
                            spacing: 6

                            Text {
                                width: 78
                                text: lineRow.modelData && lineRow.modelData.label ? lineRow.modelData.label : ""
                                color: Theme.textFaint
                                font.pixelSize: Theme.fontSizeSm
                                elide: Text.ElideRight
                            }

                            Text {
                                width: Math.max(0, parent.width - 78 - parent.spacing)
                                text: lineRow.modelData && lineRow.modelData.value ? lineRow.modelData.value : ""
                                // Optional per-line tone ("good"/"bad") colors the
                                // value, e.g. DeepSeek's peak/off-peak rate flag.
                                color: lineRow.modelData && lineRow.modelData.tone === "bad" ? Theme.accentRed
                                    : lineRow.modelData && lineRow.modelData.tone === "good" ? Theme.accentGreen
                                    : Theme.text
                                font.pixelSize: Theme.fontSizeSm
                                elide: Text.ElideRight
                            }
                        }
                    }

                    Text {
                        visible: !!(card.modelData && card.modelData.note && card.modelData.status !== "ok")
                        width: parent.width
                        wrapMode: Text.Wrap
                        text: card.modelData && card.modelData.note ? card.modelData.note : ""
                        color: Theme.textFaint
                        font.pixelSize: Theme.fontSizeSm
                    }
                }
            }
        }

        Text {
            visible: root.expanded && !AiSpend.ready
            width: parent.width
            wrapMode: Text.Wrap
            text: AiSpend.queryFailed
                ? ("Spend query unavailable" + (AiSpend.failNote ? " — " + AiSpend.failNote : ""))
                : "Reading AI spend…"
            color: Theme.textFaint
            font.pixelSize: Theme.fontSizeSm
        }
    }
}
