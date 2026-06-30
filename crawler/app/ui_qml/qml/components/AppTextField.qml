import QtQuick
import QtQuick.Controls.Basic
import ".." as Ui

TextField {
    id: control
    property string size: "default"

    implicitHeight: size === "compact" ? 32 : 44
    Accessible.role: Accessible.EditableText
    Accessible.name: placeholderText
    color: enabled ? Ui.Theme.text : Ui.Theme.textMuted
    placeholderTextColor: Ui.Theme.textMuted
    selectionColor: Ui.Theme.accent
    selectedTextColor: "white"
    leftPadding: size === "compact" ? 8 : 12
    rightPadding: size === "compact" ? 8 : 12

    background: Rectangle {
        color: control.enabled ? Ui.Theme.surfaceRaised : Ui.Theme.surface
        border.color: control.activeFocus ? Ui.Theme.accent
                      : control.hovered ? Ui.Theme.textMuted : Ui.Theme.border
        border.width: 1
        radius: Ui.Theme.radiusSmall
    }
}
