pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import ".." as Ui

ListView {
    id: root
    required property var viewModel
    readonly property bool compact: width < 720
    property real firstRowHeight: 0
    property real firstRowContentHeight: 0
    clip: true
    spacing: 5
    Accessible.name: "필드 매핑 목록"
    delegate: Rectangle {
        id: mappingRow
        required property string key
        required property string label
        required property string selector
        required property string status
        required property string testValue
        required property bool testOk
        required property int index
        objectName: "mappingRow-" + index
        readonly property real contentImplicitHeight: content.implicitHeight
        function publishGeometry() {
            if (index === 0) {
                root.firstRowHeight = height
                root.firstRowContentHeight = contentImplicitHeight
            }
        }
        Component.onCompleted: publishGeometry()
        onHeightChanged: publishGeometry()
        width: ListView.view.width
        height: Math.max(root.compact ? 104 : 72, contentImplicitHeight + 18)
        radius: 8
        color: Ui.Theme.surfaceRaised
        border.color: Ui.Theme.border
        ColumnLayout {
            id: content
            onImplicitHeightChanged: mappingRow.publishGeometry()
            anchors.fill: parent
            anchors.margins: 9
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                Text { text: mappingRow.label; color: Ui.Theme.text; font.weight: Font.DemiBold }
                Text { text: mappingRow.status; color: mappingRow.status === "ok" ? Ui.Theme.success : Ui.Theme.warning; font.pixelSize: 11 }
                Text {
                    Layout.fillWidth: true
                    text: mappingRow.testValue || mappingRow.selector || "선택자 없음"
                    color: mappingRow.testValue ? (mappingRow.testOk ? Ui.Theme.success : Ui.Theme.danger) : Ui.Theme.textMuted
                    elide: Text.ElideRight
                    font.family: "monospace"
                }
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Layout.fillWidth: root.compact
                AppButton { Layout.fillWidth: root.compact; text: "선택"; enabled: !root.viewModel.busy; onClicked: root.viewModel.pickElement("adapter.product." + mappingRow.key) }
                AppButton { Layout.fillWidth: root.compact; text: "테스트"; enabled: !root.viewModel.busy; onClicked: root.viewModel.testSingle(mappingRow.key) }
            }
        }
    }
}
