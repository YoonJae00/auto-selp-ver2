import QtQuick
import QtQuick.Layouts
import ".." as Ui

ColumnLayout {
    property string title: "표시할 내용이 없습니다"
    property string description: "작업을 시작하면 여기에 결과가 표시됩니다."
    spacing: 6

    Text {
        Layout.alignment: Qt.AlignHCenter
        text: parent.title
        color: Ui.Theme.text
        font.pixelSize: 15
        font.weight: Font.DemiBold
    }
    Text {
        Layout.alignment: Qt.AlignHCenter
        text: parent.description
        color: Ui.Theme.textMuted
        font.pixelSize: 12
    }
}
