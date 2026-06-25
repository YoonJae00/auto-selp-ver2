import QtQuick
import ".." as Ui

Item {
    id: root
    property string message: ""
    property string severity: "info"

    function showMessage(text, kind) {
        message = text
        severity = kind || "info"
        toast.visible = true
        hideTimer.restart()
    }

    Rectangle {
        id: toast
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        width: Math.min(360, toastText.implicitWidth + 32)
        height: toastText.implicitHeight + 24
        visible: false
        color: Ui.Theme.surfaceRaised
        border.color: root.severity === "danger" ? Ui.Theme.danger : Ui.Theme.border
        border.width: 1
        radius: Ui.Theme.radiusMedium

        Text {
            id: toastText
            anchors.centerIn: parent
            width: parent.width - 32
            text: root.message
            color: Ui.Theme.text
            wrapMode: Text.Wrap
            font.pixelSize: 12
        }
    }
    Timer {
        id: hideTimer
        interval: 2800
        onTriggered: toast.visible = false
    }
}
