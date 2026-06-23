pragma Singleton

import QtQuick
import QtQuick.Controls

QtObject {
    readonly property bool dark: Application.styleHints.colorScheme === Qt.ColorScheme.Dark

    readonly property color canvas: dark ? "#111318" : "#F4F6F8"
    readonly property color surface: dark ? "#191C23" : "#FFFFFF"
    readonly property color surfaceRaised: dark ? "#222630" : "#F9FAFB"
    readonly property color border: dark ? "#343946" : "#DDE2E8"
    readonly property color text: dark ? "#F3F5F7" : "#1B2028"
    readonly property color textMuted: dark ? "#A4ADBA" : "#657080"
    readonly property color accent: dark ? "#7BA7FF" : "#336FE5"
    readonly property color success: dark ? "#52D69A" : "#168A5B"
    readonly property color warning: dark ? "#F4C75C" : "#A96800"
    readonly property color danger: dark ? "#FF7E88" : "#C83745"

    readonly property int radiusSmall: 8
    readonly property int radiusMedium: 10
    readonly property int radiusLarge: 12
    readonly property int motionFast: 120
    readonly property int motionNormal: 180
}
