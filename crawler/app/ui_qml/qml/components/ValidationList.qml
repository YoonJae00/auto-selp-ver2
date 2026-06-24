pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import ".." as Ui

ListView {
    id: root
    property string accessibleName: "내보내기 검증 결과"
    signal issueActivated(int index)
    clip: true
    reuseItems: true
    spacing: 4
    Accessible.role: Accessible.List
    Accessible.name: accessibleName
    delegate: Rectangle {
        id: issueRow
        required property var model
        required property int index
        width: ListView.view.width
        height: 48
        radius: Ui.Theme.radiusSmall
        color: model.severity === "error" ? Qt.alpha(Ui.Theme.dangerForeground, 0.1) : Qt.alpha(Ui.Theme.warningForeground, 0.1)
        Accessible.role: Accessible.ListItem
        Accessible.name: (model.severity === "error" ? "오류 " : "경고 ") + model.message
        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            Text { text: issueRow.model.severity === "error" ? "오류" : "경고"; color: issueRow.model.severity === "error" ? Ui.Theme.dangerForeground : Ui.Theme.warningForeground; font.bold: true }
            Text { Layout.fillWidth: true; text: issueRow.model.message; color: Ui.Theme.text; elide: Text.ElideRight }
            Text { text: issueRow.model.productCode; color: Ui.Theme.textMuted }
        }
        TapHandler { onTapped: root.issueActivated(issueRow.index) }
    }
}
