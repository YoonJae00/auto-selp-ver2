import QtQuick
import QtQuick.Layouts
import ".." as Ui

GlassPanel {
    id: root
    property string title: "상세 정보"

    width: Math.min(340, parent ? parent.width * 0.86 : 340)
    radius: 0
    color: Ui.Theme.surfaceRaised

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 10
        Text {
            text: root.title
            color: Ui.Theme.text
            font.pixelSize: 18
            font.weight: Font.Bold
        }
        Text {
            Layout.fillWidth: true
            text: "선택한 항목의 상세 정보가 여기에 표시됩니다."
            color: Ui.Theme.textMuted
            wrapMode: Text.Wrap
            font.pixelSize: 13
        }
        Item { Layout.fillHeight: true }
    }
}
