pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import ".." as Ui

ListView {
    id: root
    required property var viewModel
    model: viewModel.results
    clip: true
    reuseItems: true
    spacing: 1
    Accessible.name: "수집 결과"
    delegate: Rectangle {
        id: resultRow
        required property int index
        required property string name
        required property string code
        required property int optionCount
        width: ListView.view.width
        height: 38
        color: resultRow.index % 2 ? Ui.Theme.surfaceRaised : "transparent"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            Text { Layout.fillWidth: true; text: resultRow.name; color: Ui.Theme.text; elide: Text.ElideRight }
            Text { Layout.preferredWidth: 100; text: resultRow.code; color: Ui.Theme.textMuted; elide: Text.ElideRight }
            Text { Layout.preferredWidth: 55; text: resultRow.optionCount + "개"; color: Ui.Theme.accent; horizontalAlignment: Text.AlignRight }
        }
    }
}
