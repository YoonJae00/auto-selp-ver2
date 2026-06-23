import QtQuick
import QtQuick.Controls.Basic
import ".." as Ui

Dialog {
    id: root
    property string message: "계속하시겠습니까?"
    signal confirmed()

    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel
    onAccepted: confirmed()

    contentItem: Text {
        text: root.message
        color: Ui.Theme.text
        wrapMode: Text.Wrap
        padding: 16
    }
    background: Rectangle {
        color: Ui.Theme.surface
        border.color: Ui.Theme.border
        border.width: 1
        radius: Ui.Theme.radiusLarge
    }
}
