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
        required property string fieldPath
        required property string selector
        required property string status
        required property string testValue
        required property bool testOk
        required property int index
        required property string urlPattern
        required property bool urlAllowed
        required property bool testable
        required property bool extraEnabled
        objectName: "mappingRow-" + index
        readonly property var vm: ListView.view.viewModel
        readonly property real contentImplicitHeight: content.implicitHeight
        property bool urlMode: urlPattern !== ""
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
        readonly property bool pickingActive: mappingRow.vm.pickerActive && mappingRow.vm.pickerFieldLabel === mappingRow.label
        color: pickingActive ? Qt.alpha(Ui.Theme.accent, 0.10) : Ui.Theme.surfaceRaised
        border.color: pickingActive ? Ui.Theme.accent : Ui.Theme.border
        ColumnLayout {
            id: content
            onImplicitHeightChanged: mappingRow.publishGeometry()
            anchors.fill: parent
            anchors.margins: 8
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Text {
                    text: mappingRow.label
                    color: Ui.Theme.text
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    Layout.preferredWidth: 88
                    elide: Text.ElideRight
                }
                CheckBox {
                    visible: mappingRow.key === "extra_image_urls"
                    checked: mappingRow.extraEnabled
                    enabled: !mappingRow.vm.busy
                    text: ""
                    ToolTip.text: checked ? "추가 이미지 수집 사용" : "추가 이미지 수집 안 함"
                    onToggled: mappingRow.vm.setExtraImagesEnabled(checked)
                }
                Text {
                    text: mappingRow.status === "ok" ? "●" : "○"
                    color: mappingRow.status === "ok" ? Ui.Theme.success : Ui.Theme.warning
                    font.pixelSize: 10
                    Layout.preferredWidth: 14
                }
                Text {
                    Layout.fillWidth: true
                    text: mappingRow.urlMode ? ("URL: " + (mappingRow.urlPattern || "패턴 없음")) : (mappingRow.testValue || mappingRow.selector || "선택자 없음")
                    color: mappingRow.urlMode ? Ui.Theme.accent : (mappingRow.testValue ? (mappingRow.testOk ? Ui.Theme.success : Ui.Theme.danger) : Ui.Theme.textMuted)
                    elide: Text.ElideRight
                    font.family: "monospace"
                    font.pixelSize: 11
                }
                AppButton {
                    size: "compact"
                    text: "선택"
                    enabled: !mappingRow.vm.busy && !mappingRow.urlMode && (mappingRow.key !== "extra_image_urls" || mappingRow.extraEnabled)
                    ToolTip.text: "브라우저에서 이 필드의 요소를 직접 클릭하여 선택합니다"
                    onClicked: mappingRow.vm.pickElement(mappingRow.fieldPath)
                }
                AppButton {
                    visible: mappingRow.urlAllowed
                    size: "compact"
                    text: mappingRow.urlMode ? "URL ✓" : "URL"
                    highlighted: mappingRow.urlMode
                    ToolTip.text: mappingRow.urlMode ? "URL 패턴 모드 해제" : "URL에서 값 추출 (상품코드 등)"
                    onClicked: {
                        if (mappingRow.urlMode) {
                            mappingRow.urlMode = false
                            mappingRow.vm.setFieldUrlPattern(mappingRow.key, "")
                        } else {
                            mappingRow.urlMode = true
                        }
                    }
                }
                AppButton {
                    visible: mappingRow.testable
                    size: "compact"
                    text: "테스트"
                    enabled: !mappingRow.vm.busy
                    onClicked: mappingRow.vm.testSingle(mappingRow.key)
                }
            }
            TextField {
                visible: mappingRow.urlMode
                Layout.fillWidth: true
                placeholderText: "정규식 예: goodsno=(\\d+)"
                text: mappingRow.urlPattern
                font.family: "monospace"
                font.pixelSize: 11
                onEditingFinished: mappingRow.vm.setFieldUrlPattern(mappingRow.key, text)
            }
        }
    }
}
