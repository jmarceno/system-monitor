pragma Singleton
import Quickshell
import QtQuick

// Palette matching mock/mockup.png (dark navy, cyan accents).
Singleton {
    id: root

    // Window chrome
    readonly property color windowBg: "#0d1526"
    readonly property color windowBorder: "#1e2a44"

    // Cards
    readonly property color cardBg: "#0f1930"
    readonly property color cardBorder: "#1e2a44"
    readonly property color cardHighlightBg: "#0c2030"
    readonly property color cardHighlightBorder: "#22d3ee"

    // Accents
    readonly property color accentCyan: "#22d3ee"
    readonly property color accentBlue: "#3b82f6"
    readonly property color accentAmber: "#f5b942"
    readonly property color accentGreen: "#22c55e"
    readonly property color accentRed: "#ef4444"

    // Text
    readonly property color text: "#e2e8f0"
    readonly property color textMuted: "#94a3b8"
    readonly property color textFaint: "#64748b"

    // Bars / tracks
    readonly property color track: "#1b2942"

    readonly property string fontFamily: "Noto Sans"
    readonly property int fontSizeSm: 9
    readonly property int fontSizeMd: 10
    readonly property int fontSizeLg: 12
    readonly property int fontSizeXl: 14
}
