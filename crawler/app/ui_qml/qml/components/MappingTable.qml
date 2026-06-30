pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

ListView {
    id: root
    required property var viewModel
    property real firstRowHeight: 0
    property real firstRowContentHeight: 0
    clip: true
    spacing: 4
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
        height: Math.max(40, contentImplicitHeight + 16)
        radius: 6
        readonly property bool pickingActive: root.viewModel.pickerActive && root.viewModel.pickerFieldLabel === mappingRow.label
        color: pickingActive ? Qt.alpha(Ui.Theme.accent, 0.10) : Ui.Theme.surfaceRaised
        border.color: pickingActive ? Ui.Theme.accent : Ui.Theme.border
        RowLayout {
            id: content
            onImplicitHeightChanged: mappingRow.publishGeometry()
            anchors.fill: parent
            anchors.margins: 8
            spacing: 8
            Text {
                text: mappingRow.label
                color: Ui.Theme.text
                font.pixelSize: 12
                font.weight: Font.DemiBold
                Layout.preferredWidth: 88
                elide: Text.ElideRight
            }
            Text {
                text: mappingRow.status === "ok" ? "●" : "○"
                color: mappingRow.status === "ok" ? Ui.Theme.success : Ui.Theme.warning
                font.pixelSize: 10
                Layout.preferredWidth: 14
            }
            Text {
                Layout.fillWidth: true
                text: mappingRow.testValue || mappingRow.selector || "선택자 없음"
                color: mappingRow.testValue ? (mappingRow.testOk ? Ui.Theme.success : Ui.Theme.danger) : Ui.Theme.textMuted
                elide: Text.ElideRight
                font.family: "monospace"
                font.pixelSize: 11
            }
            AppButton {
                size: "compact"
                text: "선택"
                enabled: !root.viewModel.busy
                ToolTip.text: "브라우저에서 이 필드의 요소를 직접 클릭하여 선택합니다"
                onClicked: root.viewModel.pickElement("adapter.product." + mappingRow.key)
            }
            AppButton {
                size: "compact"
                text: "테스트"
                enabled: !root.viewModel.busy
                onClicked: root.viewModel.testSingle(mappingRow.key)
            }
        }
    }
}
