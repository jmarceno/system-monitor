import QtQuick
import ".."
import "../lib/Format.js" as Format
import Quickshell
import "."
import "../service"

// Free-floating desktop widget.
//
// Implemented as an anchored layer-shell PanelWindow (Quickshell/Wayland)
// rather than the mockup's nominal FloatingWindow, because on Wayland a
// FloatingWindow can neither be programmatically positioned nor persist its
// position, and it always floats above application windows. A PanelWindow
// with left+top anchors and margin-based position gives us:
//   - drag-to-anywhere with the compositor (KWin) fully in charge,
//   - position persistence via PersistentProperties,
//   - "desktop furniture" behavior by default (below app windows), with the
//     pin button raising it above via `aboveWindows`.
// Safety contract: this is an ordinary user process alongside plasmashell;
// close button quits the instance (the systemd kill switch equivalent).
PanelWindow {
    id: win

    anchors {
        left: true
        top: true
        right: false
        bottom: false
    }
    exclusionMode: ExclusionMode.Ignore
    focusable: false
    aboveWindows: persist.pinned
    color: "transparent"

    implicitWidth: persist.collapsed ? Config.collapsedWidth : Config.windowWidth
    implicitHeight: persist.collapsed
        ? collapsedPill.implicitHeight + 12
        : contentCol.implicitHeight + 16

    margins.left: persist.posX
    margins.top: persist.posY

    PersistentProperties {
        id: persist
        reloadableId: "monitorWindow"

        property int posX: 24
        property int posY: 24
        property bool pinned: false
        property bool collapsed: false
    }

    // Full view
    Rectangle {
        id: fullCard
        visible: !persist.collapsed
        anchors.fill: parent
        radius: 14
        color: Theme.windowBg
        border.width: 1
        border.color: Theme.windowBorder

        Column {
            id: contentCol
            anchors.fill: parent
            anchors.margins: 8
            spacing: 8

            HeaderBar {
                width: parent.width
                win: win
                persist: persist
                onCollapseToggled: persist.collapsed = true
                onPinToggled: persist.pinned = !persist.pinned
                onCloseRequested: Qt.quit()
                onDragFinished: (mx, my) => win._handleDrop(mx, my)
            }

            TopStrip { width: parent.width }
            MemoryCard { width: parent.width }
            SwapAttributionCard { width: parent.width }
            ZramCard { width: parent.width }
            VramCard { width: parent.width }
        }
    }

    // Collapsed pill
    Rectangle {
        id: collapsedPill
        visible: persist.collapsed
        anchors.fill: parent
        radius: 16
        color: Theme.windowBg
        border.width: 1
        border.color: Theme.windowBorder

        Row {
            anchors.centerIn: parent
            spacing: 10

            Text {
                text: "∿"
                color: Theme.accentCyan
                font.pixelSize: 14
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: "R " + Math.round(MemInfo.usedPct) + "%"
                color: Theme.accentBlue
                font.pixelSize: Theme.fontSizeSm
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: "z " + (Zram.ready ? Format.fmtBytes(Zram.memUsedBytes) : "…")
                color: Theme.accentCyan
                font.pixelSize: Theme.fontSizeSm
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: "D " + (SwapDisk.hasSample ? Format.fmtRateKBps(SwapDisk.diskSwapOutKBps) : "…")
                color: SwapDisk.verdict === 3 ? Theme.accentRed : Theme.accentGreen
                font.pixelSize: Theme.fontSizeSm
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: "V " + (Vram.available ? Math.round(Vram.usedPct) + "%" : "n/a")
                color: Theme.accentAmber
                font.pixelSize: Theme.fontSizeSm
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
        }

        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: persist.collapsed = false
        }
    }

    Component.onCompleted: {
        SystemSnapshot.compactMode = Qt.binding(function () { return persist.collapsed; });
        _clampToScreen();
    }

    onWidthChanged: _clampToScreen()

    // Drag may end over a different monitor. Layer-shell surfaces are bound
    // to one output, so on drop we check which screen the cursor is over and
    // hand the widget off: reassign `screen`, then rebase the margins on the
    // new screen's top-left so the widget lands under the cursor.
    function _handleDrop(mouseX, mouseY) {
        if (!win.screen || Quickshell.screens.length < 2)
            return;

        // Window-content offset: HeaderBar sits inside contentCol (margins 8).
        const contentOffset = 8;
        const cursorGlobalX = win.screen.x + win.margins.left + contentOffset + mouseX;
        const cursorGlobalY = win.screen.y + win.margins.top + contentOffset + mouseY;
        // grab offset = cursor position relative to the window's top-left
        const grabX = contentOffset + mouseX;
        const grabY = contentOffset + mouseY;

        const target = _screenAt(cursorGlobalX, cursorGlobalY);
        if (!target || target === win.screen)
            return;

        win.screen = target;
        persist.posX = Math.round(Format.clamp(cursorGlobalX - grabX - target.x, 0, Math.max(0, target.width - win.width)));
        persist.posY = Math.round(Format.clamp(cursorGlobalY - grabY - target.y, 0, Math.max(0, target.height - win.height)));
    }

    function _screenAt(globalX, globalY) {
        for (let i = 0; i < Quickshell.screens.length; i++) {
            const s = Quickshell.screens[i];
            if (globalX >= s.x && globalX < s.x + s.width && globalY >= s.y && globalY < s.y + s.height)
                return s;
        }
        return null;
    }

    function _clampToScreen() {
        if (!win.screen)
            return;
        persist.posX = Math.round(Format.clamp(persist.posX, 0, Math.max(0, win.screen.width - win.width)));
        persist.posY = Math.round(Format.clamp(persist.posY, 0, Math.max(0, win.screen.height - win.height)));
    }
}
