pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import ".." as Ui

ListView {
    id: root
    property string accessibleName: "내보내기 검증 결과"
    signal issueActivated(int index)
    clip: true
    activeFocusOnTab: true
    reuseItems: true
    spacing: 4
    Accessible.role: Accessible.List
    Accessible.name: accessibleName
    Keys.onReturnPressed: event => { if (currentIndex >= 0) root.issueActivated(currentIndex); event.accepted = true }
    Keys.onEnterPressed: event => { if (currentIndex >= 0) root.issueActivated(currentIndex); event.accepted = true }
    Keys.onSpacePressed: event => { if (currentIndex >= 0) root.issueActivated(currentIndex); event.accepted = true }
    delegate: Rectangle {
        id: issueRow
        objectName: "exportValidationIssue-" + index
        required property var model
        required property int index
        width: ListView.view.width
        height: 48
        activeFocusOnTab: true
        focus: ListView.isCurrentItem
        radius: Ui.Theme.radiusSmall
        color: model.severity === "error" ? Qt.alpha(Ui.Theme.dangerForeground, 0.1) : Qt.alpha(Ui.Theme.warningForeground, 0.1)
        Accessible.role: Accessible.ListItem
        Accessible.name: (model.severity === "error" ? "오류 " : "경고 ") + model.message
        Accessible.onPressAction: root.issueActivated(issueRow.index)
        Keys.onReturnPressed: event => { root.issueActivated(issueRow.index); event.accepted = true }
        Keys.onEnterPressed: event => { root.issueActivated(issueRow.index); event.accepted = true }
        Keys.onSpacePressed: event => { root.issueActivated(issueRow.index); event.accepted = true }
        RowLayout {
            anchors.fill: parent
            anchors.margins: 8
            Text { text: issueRow.model.severity === "error" ? "오류" : "경고"; color: issueRow.model.severity === "error" ? Ui.Theme.dangerForeground : Ui.Theme.warningForeground; font.bold: true }
            Text { Layout.fillWidth: true; text: issueRow.model.message; color: Ui.Theme.text; elide: Text.ElideRight }
            Text { text: issueRow.model.productCode; color: Ui.Theme.textMuted }
        }
        TapHandler { onTapped: { issueRow.ListView.view.currentIndex = issueRow.index; issueRow.forceActiveFocus(); root.issueActivated(issueRow.index) } }
    }
}
