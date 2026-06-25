import QtQuick
import QtQuick.Controls.Basic
import ".." as Ui

Button {
    id: control
    property bool selected: false

    implicitHeight: 44
    implicitWidth: Math.max(72, contentItem.implicitWidth + 24)
    hoverEnabled: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    ToolTip.visible: hovered && ToolTip.text.length > 0
    ToolTip.delay: 500

    contentItem: Text {
        text: control.text
        color: !control.enabled ? Ui.Theme.textMuted
              : control.selected ? Ui.Theme.accent : Ui.Theme.text
        font.pixelSize: 13
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
