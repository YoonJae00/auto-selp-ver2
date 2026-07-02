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
        required property string urlParam
        required property bool urlAllowed
        required property bool testable
        required property bool extraEnabled
        objectName: "mappingRow-" + index
        readonly property var vm: ListView.view.viewModel
        readonly property real contentImplicitHeight: content.implicitHeight
        property bool urlMode: urlPattern !== "" || urlParam !== ""
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
                    text: mappingRow.urlMode ? ("URL: " + (mappingRow.urlParam ? ("파라미터 " + mappingRow.urlParam) : (mappingRow.urlPattern || "미설정"))) : (mappingRow.testValue || mappingRow.selector || "선택자 없음")
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
                            mappingRow.vm.setFieldUrlParam(mappingRow.key, "")
                            mappingRow.vm.setFieldUrlPattern(mappingRow.key, "")
                        } else {
                            mappingRow.urlMode = true
                        }
                    }
                }
                AppButton {
                    visible: mappingRow.key === "supplier_status"
                    size: "compact"
                    text: mappingRow.vm.soldoutCompareOpen ? "닫기" : "품절 비교"
                    enabled: !mappingRow.vm.busy
                    ToolTip.text: "품절 상품 URL을 입력해 판매 상태 매핑을 AI가 비교합니다"
                    onClicked: mappingRow.vm.setSoldoutCompareOpen(!mappingRow.vm.soldoutCompareOpen)
                }
                AppButton {
                    visible: mappingRow.testable
                    size: "compact"
                    text: "테스트"
                    enabled: !mappingRow.vm.busy
                    onClicked: mappingRow.vm.testSingle(mappingRow.key)
                }
            }
            ColumnLayout {
                id: urlArea
                visible: mappingRow.urlMode
                Layout.fillWidth: true
                spacing: 4
                property var urlOptions: mappingRow.urlMode ? mappingRow.vm.urlParamOptions() : []
                property bool advancedOpen: mappingRow.urlPattern !== ""

                Text {
                    Layout.fillWidth: true
                    visible: urlArea.urlOptions.length === 0
                    text: "이 URL에 파라미터가 없습니다 — 아래 '직접 입력(고급)'을 사용하세요."
                    color: Ui.Theme.textMuted
                    wrapMode: Text.WordWrap
                    font.pixelSize: 11
                }
                ComboBox {
                    visible: urlArea.urlOptions.length > 0
                    Layout.fillWidth: true
                    model: urlArea.urlOptions
                    textRole: "display"
                    font.pixelSize: 11
                    currentIndex: {
                        for (var i = 0; i < urlArea.urlOptions.length; i++)
                            if (urlArea.urlOptions[i].name === mappingRow.urlParam)
                                return i
                        return -1
                    }
                    displayText: currentIndex < 0 ? "상품코드에 해당하는 파라미터를 선택하세요" : currentText
                    onActivated: mappingRow.vm.setFieldUrlParam(mappingRow.key, urlArea.urlOptions[currentIndex].name)
                }
                AppButton {
                    size: "compact"
                    text: urlArea.advancedOpen ? "직접 입력 닫기" : "직접 입력(고급)"
                    ToolTip.text: "상품코드가 경로(예: /product/12345)에 있을 때 정규식으로 직접 입력"
                    onClicked: urlArea.advancedOpen = !urlArea.advancedOpen
                }
                TextField {
                    visible: urlArea.advancedOpen
                    Layout.fillWidth: true
                    placeholderText: "정규식 예: goodsno=(\\d+)"
                    text: mappingRow.urlPattern
                    font.family: "monospace"
                    font.pixelSize: 11
                    onEditingFinished: mappingRow.vm.setFieldUrlPattern(mappingRow.key, text)
                }
            }
            ColumnLayout {
                id: soldoutArea
                visible: mappingRow.key === "supplier_status" && mappingRow.vm.soldoutCompareOpen
                Layout.fillWidth: true
                spacing: 6
                Text {
                    Layout.fillWidth: true
                    text: "품절 상품 URL을 입력하면 현재 매핑 대상 상품 URL과 비교해 판매 상태 매핑을 제안합니다."
                    color: Ui.Theme.textMuted
                    wrapMode: Text.WordWrap
                    font.pixelSize: 11
                }
                AppTextField {
                    id: soldoutUrlField
                    Layout.fillWidth: true
                    text: mappingRow.vm.soldoutUrl || ""
                    placeholderText: "품절 상품 상세 페이지 URL"
                    Accessible.name: "품절 상품 URL"
                    size: "compact"
                    onEditingFinished: mappingRow.vm.setSoldoutUrl(text)
                }
                RowLayout {
                    Layout.fillWidth: true
                    AppButton {
                        size: "compact"
                        text: "AI 분석"
                        highlighted: true
                        enabled: !mappingRow.vm.busy && soldoutUrlField.text.length > 0
                        onClicked: {
                            mappingRow.vm.setSoldoutUrl(soldoutUrlField.text)
                            mappingRow.vm.compareSoldoutStatus()
                        }
                    }
                    Item { Layout.fillWidth: true }
                }
                InlineBanner {
                    Layout.fillWidth: true
                    visible: Boolean(mappingRow.vm.soldoutSuggestion.confidence)
                    text: "신뢰도 " + (mappingRow.vm.soldoutSuggestion.confidence || "-") + " · " + (mappingRow.vm.soldoutSuggestion.note || "")
                    severity: mappingRow.vm.soldoutSuggestion.confidence === "low" ? "warning" : "info"
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: Boolean(mappingRow.vm.soldoutSuggestion.confidence)
                    Text {
                        Layout.fillWidth: true
                        text: (mappingRow.vm.soldoutSuggestion.selector || mappingRow.vm.soldoutSuggestion.fallback_from || "")
                        color: Ui.Theme.textMuted
                        font.family: "monospace"
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                    AppButton {
                        size: "compact"
                        text: "적용"
                        enabled: !mappingRow.vm.busy && mappingRow.vm.soldoutSuggestion.confidence !== "low"
                        onClicked: mappingRow.vm.acceptSoldoutSuggestion()
                    }
                    AppButton {
                        size: "compact"
                        text: "무시"
                        enabled: !mappingRow.vm.busy
                        onClicked: mappingRow.vm.rejectSoldoutSuggestion()
                    }
                }
            }
        }
    }
}
