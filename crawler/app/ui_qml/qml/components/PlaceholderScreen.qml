import QtQuick
import QtQuick.Layouts
import ".." as Ui

GlassPanel {
    id: root
    property string title: ""

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 8
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: root.title
            color: Ui.Theme.text
            font.pixelSize: 18
            font.weight: Font.DemiBold
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: "화면 준비 중"
            color: Ui.Theme.textMuted
            font.pixelSize: 13
        }
    }
}
