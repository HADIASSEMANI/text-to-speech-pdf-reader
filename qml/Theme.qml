pragma Singleton

import QtQuick

/*
   Design tokens for the reader.

   These are the values app.qss carried as literals in every rule. Keeping
   them in one place is what lets a screen be restyled without hunting for
   the same near-black in four files.
*/
QtObject {
    // Surfaces, darkest first. Page chrome sits on `background`; anything
    // that should read as raised picks the next rung up.
    readonly property color background: "#0d0f12"
    readonly property color surface: "#12151a"
    readonly property color surfaceRaised: "#15181d"
    readonly property color surfaceHigh: "#191c21"
    readonly property color surfaceHover: "#22262d"

    readonly property color border: "#292e36"
    readonly property color borderStrong: "#383f49"

    readonly property color text: "#e6e8eb"
    readonly property color textMuted: "#b9bec7"
    readonly property color textFaint: "#8c929b"
    readonly property color textDisabled: "#5a5f68"

    readonly property color accent: "#6695ff"
    readonly property color highlight: "#2a3140"
    readonly property color highlightText: "#ffffff"

    readonly property color danger: "#ff557f"
    readonly property color dangerBorder: "#3a2a2d"

    // Spacing scale. Screens use these rather than arbitrary numbers so
    // rhythm survives a layout change.
    readonly property int spacingTight: 8
    readonly property int spacingSmall: 12
    readonly property int spacing: 20
    readonly property int spacingLarge: 24
    readonly property int pageMargin: 32

    readonly property int radiusSmall: 8
    readonly property int radius: 12
    readonly property int radiusLarge: 16

    readonly property int fontSizeSmall: 12
    readonly property int fontSizeBody: 14
    readonly property int fontSizeReader: 18
    readonly property int fontSizeTitle: 20
    readonly property int fontSizeDisplay: 30

    readonly property string fontFamily: "Segoe UI"

    // Below this the reader stacks its controls and the library drops to a
    // single column. One number, so every screen breaks at the same width.
    readonly property int narrowWidth: 720

    readonly property int transitionDuration: 160
}
