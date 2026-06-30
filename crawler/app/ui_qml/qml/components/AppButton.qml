import QtQuick
import QtQuick.Controls.Basic
import ".." as Ui

Button {
    id: control
    property bool selected: false
    property string size: "default"

    implicitHeight: size === "compact" ? 28 : 44
    implicitWidth: Math.max(size === "compact" ? 56 : 72, contentItem.implicitWidth + (size === "compact" ? 16 : 24))
    hoverEnabled: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    ToolTip.visible: hovered && ToolTip.text.length > 0
    ToolTip.delay: 500

    contentItem: Text {
        text: control.text
        color: !control.enabled ? Ui.Theme.textMuted
              : control.selected ? Ui.Theme.accent : Ui.Theme.text
        font.pixelSize: control.size === "compact" ? 12 : 13
        font.weight: control.selected ? Font.DemiBold : Font.Normal
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        color: !control.enabled ? "transparent"
              : control.down ? Qt.alpha(Ui.Theme.accent, 0.22)
              : control.selected ? Qt.alpha(Ui.Theme.accent, 0.14)
              : control.hovered ? Ui.Theme.surfaceRaised : "transparent"
        border.width: control.activeFocus ? 1 : 0
        border.color: Ui.Theme.accent
        radius: Ui.Theme.radiusSmall
    }
}
