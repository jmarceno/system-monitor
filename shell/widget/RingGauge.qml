import QtQuick
import ".."
import "../lib/Format.js" as Format

// Small ring gauge for the top strip (CPU / RAM / Swap / VRAM).
Item {
    id: root

    property real value: 0            // 0..100
    property color ringColor: Theme.accentCyan
    property string label: ""
    property string sub: ""

    implicitWidth: ringSize + 54
    implicitHeight: ringSize
    property int ringSize: 36

    Canvas {
        id: ring
        width: parent.ringSize
        height: parent.ringSize
        anchors.verticalCenter: parent.verticalCenter
        antialiasing: true

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            ctx.lineWidth = 5;
            ctx.lineCap = "rounded";
            const cx = width / 2, cy = height / 2, r = width / 2 - 4;
            const start = 0.75 * Math.PI, span = 1.5 * Math.PI;
            ctx.strokeStyle = Qt.rgba(Theme.track.r, Theme.track.g, Theme.track.b, 1);
            ctx.beginPath();
            ctx.arc(cx, cy, r, start, start + span);
            ctx.stroke();
            const frac = Format.clamp(root.value / 100, 0, 1);
            if (frac > 0.001) {
                ctx.strokeStyle = root.ringColor;
                ctx.beginPath();
                ctx.arc(cx, cy, r, start, start + span * frac);
                ctx.stroke();
            }
        }

        Connections {
            function onValueChanged() { ring.requestPaint(); }
            target: root
        }

        Component.onCompleted: requestPaint()
    }

    Column {
        id: textCol
        anchors.left: ring.right
        anchors.leftMargin: 6
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0

        Text {
            text: root.label
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeSm
            width: parent.width
            elide: Text.ElideRight
        }
        Text {
            text: isFinite(root.value) ? Math.round(root.value) + "%" : "n/a"
            color: Theme.text
            font.pixelSize: Theme.fontSizeLg
            font.bold: true
            width: parent.width
            elide: Text.ElideRight
        }
        Text {
            text: root.sub
            color: Theme.textFaint
            font.pixelSize: Theme.fontSizeSm
            width: parent.width
            elide: Text.ElideRight
        }
    }
}
