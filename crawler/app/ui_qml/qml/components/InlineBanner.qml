import QtQuick
import ".." as Ui

Rectangle {
    id: root
    property string text: ""
    property string severity: "info"
    readonly property color semanticColor: severity === "success" ? Ui.Theme.success
                                           : severity === "warning" ? Ui.Theme.warning
                                           : severity === "danger" ? Ui.Theme.danger
                                           : Ui.Theme.accent
    readonly property color foregroundColor: severity === "success" ? Ui.Theme.successForeground
                                             : severity === "warning" ? Ui.Theme.warningForeground
                                             : severity === "danger" ? Ui.Theme.dangerForeground
                                             : semanticColor

    implicitHeight: message.implicitHeight + 20
    radius: Ui.Theme.radiusSmall
    color: Qt.alpha(semanticColor, 0.12)
    border.color: Qt.alpha(semanticColor, 0.45)
    border.width: 1

    Text {
        id: message
        anchors.fill: parent
        anchors.margins: 10
        text: root.text
        color: root.foregroundColor
        font.pixelSize: 12
        wrapMode: Text.Wrap
        verticalAlignment: Text.AlignVCenter
    }
}
