pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import ".." as Ui

ListView {
    id: root
    required property var viewModel
    model: viewModel.categories
    clip: true
    spacing: 2
    activeFocusOnTab: true
    Accessible.name: "카테고리 트리"

    delegate: CheckDelegate {
        id: row
        required property string id
        required property string name
        required property string path
        required property int depth
        required property bool selected
        required property bool hasChildren
        width: ListView.view.width
        leftPadding: 10 + depth * 18
        text: name
        checkState: selected ? Qt.Checked : Qt.Unchecked
        enabled: !root.viewModel.busy
        Accessible.name: path
        ToolTip.text: path
        ToolTip.visible: hovered
        onToggled: root.viewModel.toggleCategory(id, checkState === Qt.Checked)
        contentItem: Column {
            leftPadding: row.indicator.width + row.spacing
            Text { text: row.name; color: Ui.Theme.text; elide: Text.ElideRight; width: parent.width }
            Text { text: row.path; color: Ui.Theme.textMuted; font.pixelSize: 10; elide: Text.ElideMiddle; width: parent.width }
        }
    }
}
