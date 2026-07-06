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
    spacing: 8
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
        required property var model
        // model 경유 접근: 역할이 없는 모델(테스트 하네스 등)에서도 안전
        readonly property var imageUrls: model.imageUrls || []
        readonly property int skipFirst: model.skipFirst || 0
        objectName: "mappingRow-" + index
        readonly property var vm: ListView.view.viewModel
        readonly property real contentImplicitHeight: content.implicitHeight
        property bool urlMode: urlPattern !== "" || urlParam !== ""
        readonly property bool hasTestValue: testValue !== ""
        // 상태 칩: "매핑됨"은 실제 값이 들어왔을 때만. 선택자만 있으면 "미검증".
        readonly property string statusVariant: hasTestValue ? (testOk ? "success" : "danger") : (status === "ok" ? "neutral" : "warning")
        readonly property string statusLabel: hasTestValue ? (testOk ? "매핑됨" : "값 오류") : (status === "ok" ? "미검증" : "비어있음")
        function publishGeometry() {
            if (index === 0) {
                root.firstRowHeight = height
                root.firstRowContentHeight = contentImplicitHeight
            }
        }
        Component.onCompleted: publishGeometry()
        onHeightChanged: publishGeometry()
        width: ListView.view.width
        height: Math.max(52, contentImplicitHeight + 22)
        radius: 8
        readonly property bool pickingActive: mappingRow.vm.pickerActive && mappingRow.vm.pickerFieldLabel === mappingRow.label
        color: pickingActive ? Qt.alpha(Ui.Theme.accent, 0.10) : Ui.Theme.surfaceRaised
        border.color: pickingActive ? Ui.Theme.accent : Ui.Theme.border
        ColumnLayout {
            id: content
            onImplicitHeightChanged: mappingRow.publishGeometry()
            anchors.fill: parent
            anchors.margins: 12
            spacing: 6
            // ─── 기본 행: 상태칩 · 필드명 · 현재 값 · [선택] · [⋯] ───
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                StatusBadge {
                    variant: mappingRow.statusVariant
                    text: mappingRow.statusLabel
                }
                Text {
                    text: mappingRow.label
                    color: Ui.Theme.text
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    Layout.preferredWidth: 76
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: mappingRow.urlMode
                          ? (mappingRow.urlParam ? ("파라미터 " + mappingRow.urlParam) : (mappingRow.urlPattern || "미설정"))
                          : (mappingRow.hasTestValue ? mappingRow.testValue : (mappingRow.selector || "선택자 없음"))
                    color: mappingRow.hasTestValue ? Ui.Theme.text : Ui.Theme.textMuted
                    elide: Text.ElideRight
                    font.family: "monospace"
                    font.pixelSize: 11
                }
                CheckBox {
                    visible: mappingRow.key === "extra_image_urls"
                    checked: mappingRow.extraEnabled
                    enabled: !mappingRow.vm.busy
                    text: "수집"
                    font.pixelSize: 11
                    ToolTip.text: checked ? "추가 이미지 수집 사용" : "추가 이미지 수집 안 함"
                    onToggled: mappingRow.vm.setExtraImagesEnabled(checked)
                }
                AppButton {
                    size: "compact"
                    text: "선택"
                    selected: true
                    enabled: !mappingRow.vm.busy && !mappingRow.urlMode && (mappingRow.key !== "extra_image_urls" || mappingRow.extraEnabled)
                    ToolTip.text: "브라우저에서 이 필드의 요소를 직접 클릭하여 선택합니다"
                    onClicked: mappingRow.vm.pickElement(mappingRow.fieldPath)
                }
                AppButton {
                    id: moreButton
                    size: "compact"
                    text: "⋯"
                    ToolTip.text: "추가 동작"
                    onClicked: moreMenu.open()
                    Menu {
                        id: moreMenu
                        y: moreButton.height
                        MenuItem {
                            text: mappingRow.urlMode ? "✓ URL에서 값 추출" : "URL에서 값 추출"
                            visible: mappingRow.urlAllowed
                            height: visible ? implicitHeight : 0
                            onTriggered: {
                                if (mappingRow.urlMode) {
                                    mappingRow.urlMode = false
                                    mappingRow.vm.setFieldUrlParam(mappingRow.key, "")
                                    mappingRow.vm.setFieldUrlPattern(mappingRow.key, "")
                                } else {
                                    mappingRow.urlMode = true
                                }
                            }
                        }
                        MenuItem {
                            text: "테스트"
                            visible: mappingRow.testable
                            height: visible ? implicitHeight : 0
                            enabled: !mappingRow.vm.busy
                            onTriggered: mappingRow.vm.testSingle(mappingRow.key)
                        }
                        MenuItem {
                            text: mappingRow.vm.soldoutCompareOpen ? "품절 비교 닫기" : "품절 비교"
                            visible: mappingRow.key === "supplier_status"
                            height: visible ? implicitHeight : 0
                            enabled: !mappingRow.vm.busy
                            onTriggered: mappingRow.vm.setSoldoutCompareOpen(!mappingRow.vm.soldoutCompareOpen)
                        }
                    }
                }
            }
            // ─── 추가이미지 썸네일: 대표이미지 클릭 = 그 이미지까지 앞부분 제외 ───
            ColumnLayout {
                visible: mappingRow.key === "extra_image_urls" && (mappingRow.imageUrls || []).length > 0
                Layout.fillWidth: true
                Layout.leftMargin: 86
                spacing: 4
                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    Repeater {
                        model: mappingRow.imageUrls
                        Rectangle {
                            id: thumb
                            required property string modelData
                            required property int index
                            width: 40
                            height: 40
                            radius: 4
                            color: Ui.Theme.surfaceRaised
                            border.color: Ui.Theme.border
                            Image {
                                anchors.fill: parent
                                anchors.margins: 1
                                source: thumb.modelData
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                enabled: !mappingRow.vm.busy
                                onClicked: mappingRow.vm.setFieldSkipFirst(mappingRow.key, mappingRow.skipFirst + thumb.index + 1)
                            }
                        }
                    }
                    AppButton {
                        visible: mappingRow.skipFirst > 0
                        size: "compact"
                        text: "앞 " + mappingRow.skipFirst + "개 제외 해제"
                        enabled: !mappingRow.vm.busy
                        onClicked: mappingRow.vm.setFieldSkipFirst(mappingRow.key, 0)
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: "대표이미지가 섞여 있으면 그 썸네일을 클릭하세요 — 그 이미지까지 앞부분이 수집에서 제외됩니다."
                    color: Ui.Theme.textMuted
                    wrapMode: Text.WordWrap
                    font.pixelSize: 11
                }
            }
            // ─── URL 추출 상세 (메뉴에서 켰을 때만) ───
            ColumnLayout {
                id: urlArea
                visible: mappingRow.urlMode
                Layout.fillWidth: true
                Layout.leftMargin: 86
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
            // ─── 품절 비교 상세 (메뉴에서 켰을 때만) ───
            ColumnLayout {
                id: soldoutArea
                visible: mappingRow.key === "supplier_status" && mappingRow.vm.soldoutCompareOpen
                Layout.fillWidth: true
                Layout.leftMargin: 86
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
                    // ponytail: 테스트용 기본값 — 배포 전 뒤쪽 fallback URL 지우면 됨
                    text: mappingRow.vm.soldoutUrl || "http://localhost:9000/detail.html?product_no=103"
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
