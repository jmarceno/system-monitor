import QtQuick
import ".."
import "../lib/Format.js" as Format

// Summary ring gauge sized for a two-column top strip.
Item {
    id: root

    property real value: 0            // 0..100
    property color ringColor: Theme.accentCyan
    property string label: ""
    property string sub: ""
    // Optional Celsius reading drawn inside the ring. NaN / <=0 hides it.
    property real tempC: NaN
    // Optional list of °C values (one per GPU). When non-empty, stacked in
    // GPU order and used instead of tempC so dual-GPU boxes are not merged.
    property var temps: []

    readonly property var _tempModel: {
        const src = (root.temps && root.temps.length > 0)
            ? root.temps
            : ((isFinite(root.tempC) && root.tempC > 0) ? [root.tempC] : []);
        const out = [];
        for (let i = 0; i < src.length; i++)
            out.push({ tempC: src[i] });
        return out;
    }

    implicitWidth: ringSize + 86
    implicitHeight: ringSize
    property int ringSize: 54

    Canvas {
        id: ring
        width: parent.ringSize
        height: parent.ringSize
        anchors.verticalCenter: parent.verticalCenter
        antialiasing: true

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            ctx.lineWidth = 6;
            ctx.lineCap = "rounded";
            const cx = width / 2, cy = height / 2, r = width / 2 - 5;
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
        anchors.centerIn: ring
        spacing: 0

        Repeater {
            model: root._tempModel

            Text {
                required property var modelData
                width: ring.width - 16
                horizontalAlignment: Text.AlignHCenter
                text: isFinite(modelData.tempC) && modelData.tempC > 0 ? Format.fmtTempC(modelData.tempC) : ""
                color: Theme.textMuted
                font.pixelSize: Theme.fontSizeSm
                font.bold: true
            }
        }
    }

    Column {
        id: textCol
        anchors.left: ring.right
        anchors.leftMargin: 10
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0

        Text {
            text: root.label
            color: Theme.textMuted
            font.pixelSize: Theme.fontSizeMd
            font.bold: true
            width: parent.width
            elide: Text.ElideRight
        }
        Text {
            text: isFinite(root.value) ? Math.round(root.value) + "%" : "n/a"
            color: Theme.text
            font.pixelSize: 18
            font.bold: true
            width: parent.width
            elide: Text.ElideRight
        }
        Text {
            text: root.sub
            color: Theme.textFaint
            font.pixelSize: Theme.fontSizeMd
            width: parent.width
            elide: Text.ElideRight
        }
    }
}
