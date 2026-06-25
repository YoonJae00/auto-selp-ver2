import QtQuick
import QtQuick.Layouts
import ".." as Ui

GlassPanel {
    id: root
    property string title: ""
    property int value: 0
    property string semantic: "neutral"
    readonly property color semanticColor: semantic === "danger" ? Ui.Theme.dangerForeground
                                           : semantic === "success" ? Ui.Theme.successForeground
                                           : semantic === "warning" ? Ui.Theme.warningForeground
                                           : Ui.Theme.accent
    implicitWidth: 124
    implicitHeight: 76
    Accessible.role: Accessible.StaticText
    Accessible.name: title + ": " + value

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 3
        Text { text: root.title; color: Ui.Theme.textMuted; font.pixelSize: 11 }
        Text { text: root.value; color: root.semanticColor; font.pixelSize: 23; font.weight: Font.DemiBold }
    }
}
