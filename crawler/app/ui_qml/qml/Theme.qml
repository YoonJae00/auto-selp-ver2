pragma Singleton

import QtQuick

QtObject {
    readonly property bool dark: Application.styleHints.colorScheme === Qt.ColorScheme.Dark

    readonly property color canvas: dark ? "#171717" : "#F3F2EF"
    readonly property color surface: dark ? "#CC242424" : "#DDFDFDFC"
    readonly property color surfaceRaised: dark ? "#E62D2D2D" : "#F2FFFFFF"
    readonly property color border: dark ? "#30FFFFFF" : "#18000000"
    readonly property color text: dark ? "#F2F2F2" : "#20201F"
    readonly property color textMuted: dark ? "#A8A8A8" : "#66635F"
    readonly property color accent: dark ? "#8B9DFF" : "#5366D6"
    readonly property color success: "#3FB98B"
    readonly property color warning: "#E6A84A"
    readonly property color danger: "#E56B6F"
    readonly property color successForegroundDark: "#3FB98B"
    readonly property color warningForegroundDark: "#E6A84A"
    readonly property color dangerForegroundDark: "#E56B6F"
    readonly property color successForegroundLight: "#117A55"
    readonly property color warningForegroundLight: "#805000"
    readonly property color dangerForegroundLight: "#A52F37"
    readonly property color successForeground: dark ? successForegroundDark : successForegroundLight
    readonly property color warningForeground: dark ? warningForegroundDark : warningForegroundLight
    readonly property color dangerForeground: dark ? dangerForegroundDark : dangerForegroundLight

    readonly property int radiusSmall: 8
    readonly property int radiusMedium: 10
    readonly property int radiusLarge: 12
    readonly property int motionFast: 120
    readonly property int motionNormal: 180
    property bool motionEnabled: {
        // qmllint disable unqualified
        return typeof InitialMotionEnabled === "boolean" ? InitialMotionEnabled : true
        // qmllint enable unqualified
    }
}
