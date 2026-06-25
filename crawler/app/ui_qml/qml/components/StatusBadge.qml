import QtQuick
import ".." as Ui

Rectangle {
    id: root
    property string text: ""
    property string variant: "neutral"
    readonly property color semanticColor: variant === "success" ? Ui.Theme.success
                                           : variant === "warning" ? Ui.Theme.warning
                                           : variant === "danger" ? Ui.Theme.danger
                                           : variant === "accent" ? Ui.Theme.accent
                                           : Ui.Theme.textMuted
    readonly property color foregroundColor: variant === "success" ? Ui.Theme.successForeground
                                             : variant === "warning" ? Ui.Theme.warningForeground
                                             : variant === "danger" ? Ui.Theme.dangerForeground
                                             : semanticColor

    implicitWidth: label.implicitWidth + 16
    implicitHeight: 24
    radius: 12
    color: Qt.alpha(semanticColor, 0.14)
    border.color: Qt.alpha(semanticColor, 0.5)
    border.width: 1

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: root.foregroundColor
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }
}
