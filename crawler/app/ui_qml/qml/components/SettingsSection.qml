import QtQuick
import QtQuick.Layouts
import ".." as Ui

GlassPanel {
    id: root
    property string title: ""
    default property alias content: contentColumn.data

    implicitHeight: contentColumn.implicitHeight + 28

    ColumnLayout {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: 14
        spacing: 10

        Text {
            text: root.title
            color: Ui.Theme.text
            font.bold: true
            font.pixelSize: 16
        }
    }
}
