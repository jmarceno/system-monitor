import QtQuick
import ".."
import "../lib/Format.js" as Format

// Horizontal progress bar with rounded track (mockup style).
Rectangle {
    id: root

    property real value: 0          // 0..100
    property color fillColor: Theme.accentCyan
    readonly property real frac: Format.clamp(value / 100, 0, 1)

    width: parent.width
    height: 12
    radius: 6
    color: Theme.track

    Rectangle {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.max(parent.width * parent.frac, parent.width > 0 && parent.frac > 0 ? 8 : 0)
        radius: parent.radius
        color: parent.fillColor
        Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
    }
}
