import QtQuick
import Quickshell
import Quickshell.Io
import ".."
import "../lib/Format.js" as Format
import "."
import "../service"

// Free-floating desktop widget (controller + dynamically spawned window).
//
// Implemented as an anchored layer-shell PanelWindow rather than the mockup's
// nominal FloatingWindow, because on Wayland a FloatingWindow can neither be
// programmatically positioned nor persist its position. A PanelWindow with
// left+top anchors and margin-based position gives us:
//   - drag-to-anywhere with the compositor (KWin) fully in charge,
//   - position persistence via our own JSON state file,
//   - "desktop furniture" behavior by default (below app windows), with the
//     pin button raising it above via `aboveWindows`.
//
// Layer-shell surfaces are bound to an output at creation (a runtime
// `screen` reassignment is ignored), so moving between monitors is done by
// RECREATING the window on the target screen at drop (_handleDrop).
// Safety contract: ordinary user process alongside plasmashell; the close
// button quits the instance (systemd kill switch equivalent).
Item {
    id: ctrl

    // ---- persisted window state -------------------------------------------
    // NOTE: PersistentProperties only survives live reloads, NOT process
    // restarts — we keep our own JSON file in the Quickshell state dir
    // (debounced writes; see PLAN.md §9.3).
    QtObject {
        id: persist

        property int posX: 24
        property int posY: 24
        property bool pinned: false
        property bool collapsed: false
        property string screenName: ""

        onPosXChanged: saveTimer.restart()
        onPosYChanged: saveTimer.restart()
        onPinnedChanged: saveTimer.restart()
        onCollapsedChanged: saveTimer.restart()
    }

    property var winHandle: null
    property bool _stateLoaded: false

    // ---- state file ---------------------------------------------------------

    FileView {
        id: stateFile
        path: Quickshell.statePath("window-state.json")
        printErrors: false

        onLoaded: {
            try {
                const s = JSON.parse(text());
                if (Number.isFinite(s.posX))
                    persist.posX = s.posX;
                if (Number.isFinite(s.posY))
                    persist.posY = s.posY;
                if (typeof s.pinned === "boolean")
                    persist.pinned = s.pinned;
                if (typeof s.collapsed === "boolean")
                    persist.collapsed = s.collapsed;
                if (typeof s.screenName === "string")
                    persist.screenName = s.screenName;
            } catch (e) {
                console.warn("system-monitor: corrupt window-state.json, using defaults:", e);
            }
            ctrl._stateLoaded = true;
            ctrl._spawnWindow();
        }

        onLoadFailed: {
            ctrl._stateLoaded = true;
            ctrl._spawnWindow();
        }
    }

    Timer {
        id: saveTimer
        interval: 400 // debounce: drag updates fire many times per second
        running: false
        repeat: false
        onTriggered: ctrl._saveState()
    }

    function _saveState() {
        // setText() writes the file (atomic by default); writeAdapter() is
        // only for adapter-backed views (e.g. JsonAdapter).
        stateFile.setText(JSON.stringify({
            posX: persist.posX,
            posY: persist.posY,
            pinned: persist.pinned,
            collapsed: persist.collapsed,
            screenName: ctrl.winHandle && ctrl.winHandle.screen ? ctrl.winHandle.screen.name : persist.screenName
        }));
    }

    function _resolveScreen() {
        if (persist.screenName) {
            for (let i = 0; i < Quickshell.screens.length; i++) {
                if (Quickshell.screens[i].name === persist.screenName)
                    return Quickshell.screens[i];
            }
        }
        return null;
    }

    function _screenAt(globalX, globalY) {
        for (let i = 0; i < Quickshell.screens.length; i++) {
            const s = Quickshell.screens[i];
            if (globalX >= s.x && globalX < s.x + s.width && globalY >= s.y && globalY < s.y + s.height)
                return s;
        }
        return null;
    }

    // ---- window lifecycle ---------------------------------------------------

    Component.onCompleted: {
        SystemSnapshot.compactMode = Qt.binding(function () {
            return persist.collapsed;
        });
        // The window is spawned once the state file has been read (or failed);
        // if screens are not announced yet, onScreensChanged retries.
        if (Quickshell.screens.length > 0 && ctrl._stateLoaded)
            _spawnWindow();
    }

    Connections {
        target: Quickshell

        function onScreensChanged() {
            if (!ctrl.winHandle)
                ctrl._spawnWindow();
            else if (!ctrl._screenAt(ctrl.winHandle.screen.x, ctrl.winHandle.screen.y))
                ctrl._spawnWindow(); // current screen disappeared (hotplug)
        }
    }

    function _spawnWindow() {
        const target = _resolveScreen() || (Quickshell.screens.length > 0 ? Quickshell.screens[0] : null);
        if (!target)
            return; // no screens yet; screensChanged will retry

        const old = ctrl.winHandle;
        ctrl.winHandle = winComponent.createObject(ctrl, {
            screen: target
        });
        if (old)
            old.destroy();
    }

    function _clampToScreen() {
        const w = ctrl.winHandle;
        if (!w || !w.screen)
            return;
        persist.posX = Math.round(Format.clamp(persist.posX, 0, Math.max(0, w.screen.width - w.width)));
        persist.posY = Math.round(Format.clamp(persist.posY, 0, Math.max(0, w.screen.height - w.height)));
    }

    // Drag may end over a different monitor: hand the widget off by
    // recreating it on the target screen, position under the cursor.
    function _handleDrop(win, mouseX, mouseY) {
        if (!win.screen || Quickshell.screens.length < 2) {
            _clampToScreen();
            return;
        }

        // Window-content offset: HeaderBar sits inside contentCol (margins 8).
        const contentOffset = 8;
        const cursorGlobalX = win.screen.x + win.margins.left + contentOffset + mouseX;
        const cursorGlobalY = win.screen.y + win.margins.top + contentOffset + mouseY;
        const grabX = contentOffset + mouseX; // cursor relative to window top-left
        const grabY = contentOffset + mouseY;

        const target = _screenAt(cursorGlobalX, cursorGlobalY);
        if (!target) {
            _clampToScreen();
            return;
        }
        if (target === win.screen) {
            _clampToScreen();
            return;
        }

        persist.posX = Math.round(Format.clamp(cursorGlobalX - grabX - target.x, 0, Math.max(0, target.width - win.width)));
        persist.posY = Math.round(Format.clamp(cursorGlobalY - grabY - target.y, 0, Math.max(0, target.height - win.height)));
        persist.screenName = target.name;
        _saveState();
        _spawnWindow();
    }

    // ---- the window ---------------------------------------------------------

    Component {
        id: winComponent

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

            onWidthChanged: ctrl._clampToScreen()

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
                        onDragFinished: (mouseX, mouseY) => ctrl._handleDrop(win, mouseX, mouseY)
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
        }
    }
}
