import QtQuick
import ".."
import "../lib/Format.js" as Format

// Window header: icon, title, subtitle, window controls (− / pin / ✕).
// The whole header doubles as the drag grip — drag logic lives here and
// updates the layer-shell margins via the persisted posX/posY properties.
Rectangle {
    id: root

    // set by MonitorWindow
    property var win
    property var persist

    signal collapseToggled()
    signal pinToggled()
    signal closeRequested()

    implicitHeight: 56
    radius: 12
    color: "transparent"

    Row {
        id: titleGroup
        anchors.left: parent.left
        anchors.leftMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10

        Rectangle {
            width: 36
            height: 36
            radius: 10
            anchors.verticalCenter: parent.verticalCenter
            color: Qt.rgba(Theme.accentCyan.r, Theme.accentCyan.g, Theme.accentCyan.b, 0.13)
            border.color: Theme.accentCyan
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: "∿"
                color: Theme.accentCyan
                font.pixelSize: 20
                font.bold: true
            }
        }

        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0

            Text {
                text: "Quickshell System Monitor"
                color: Theme.text
                font.pixelSize: Theme.fontSizeXl + 1
                font.bold: true
            }
            Text {
                text: "PanelWindow · persistent position · read-only"
                color: Theme.textFaint
                font.pixelSize: Theme.fontSizeSm
            }
        }
    }

    Row {
        id: buttons
        anchors.right: parent.right
        anchors.rightMargin: 2
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        HeaderButton {
            glyph: persist && persist.collapsed ? "▣" : "—"
            onClicked: root.collapseToggled()
        }
        HeaderButton {
            glyph: "📌"
            active: persist && persist.pinned
            onClicked: root.pinToggled()
        }
        HeaderButton {
            glyph: "✕"
            onClicked: root.closeRequested()
        }
    }

    // Drag grip: update persisted position; margins bindings follow.
    MouseArea {
        anchors.fill: parent
        anchors.rightMargin: buttons.implicitWidth + 20
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor

        property real pressX: 0
        property real pressY: 0
        property int startX: 0
        property int startY: 0

        onPressed: mouse => {
            pressX = mouse.x;
            pressY = mouse.y;
            startX = win ? win.margins.left : 0;
            startY = win ? win.margins.top : 0;
        }
        onPositionChanged: mouse => {
            if (!pressed || !win || !win.screen)
                return;
            const nx = Math.round(Format.clamp(startX + mouse.x - pressX, 0, Math.max(0, win.screen.width - win.width)));
            const ny = Math.round(Format.clamp(startY + mouse.y - pressY, 0, Math.max(0, win.screen.height - win.height)));
            if (persist) {
                persist.posX = nx;
                persist.posY = ny;
            }
        }
    }

    component HeaderButton: Rectangle {
        id: btn

        property string glyph: ""
        property bool active: false
        signal clicked()

        width: 30
        height: 30
        radius: 8
        color: btnMouse.containsMouse || active
            ? (active ? Qt.rgba(Theme.accentAmber.r, Theme.accentAmber.g, Theme.accentAmber.b, 0.25) : Theme.track)
            : "transparent"
        border.width: active ? 1 : 0
        border.color: Theme.accentAmber

        Text {
            anchors.centerIn: parent
            text: btn.glyph
            color: btn.active ? Theme.accentAmber : Theme.textMuted
            font.pixelSize: 13
        }

        MouseArea {
            id: btnMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: btn.clicked()
        }
    }
}
