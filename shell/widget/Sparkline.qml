import QtQuick
import ".."

// Tiny sparkline of a bounded per-device I/O history.
Item {
    id: root

    property var history: []
    property color lineColor: Theme.accentCyan

    width: 70
    height: 24

    Canvas {
        id: canvas
        anchors.fill: parent
        antialiasing: true

        onPaint: {
            const ctx = getContext("2d");
            ctx.reset();
            ctx.lineWidth = 1.5;
            ctx.strokeStyle = root.lineColor;
            const h = root.history;
            if (!h || h.length < 2)
                return;
            let max = 1;
            for (let i = 0; i < h.length; i++)
                if (h[i] > max)
                    max = h[i];
            const step = width / (h.length - 1);
            ctx.beginPath();
            for (let i = 0; i < h.length; i++) {
                const x = i * step;
                const y = height - 2 - (height - 4) * (h[i] / max);
                if (i === 0)
                    ctx.moveTo(x, y);
                else
                    ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        Connections {
            function onHistoryChanged() { canvas.requestPaint(); }
            target: root
        }
    }
}
