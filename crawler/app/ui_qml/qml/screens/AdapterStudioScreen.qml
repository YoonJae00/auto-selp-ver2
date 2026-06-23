pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui
import "../components" as Components

Item {
    id: root
    required property var viewModel
    focus: true

    ColumnLayout {
        anchors.fill: parent
        spacing: 12
        Components.StageRail {
            Layout.fillWidth: true
            currentStage: root.viewModel.currentStage
            onStageRequested: stage => root.viewModel.setCurrentStage(stage)
        }
        Components.InlineBanner {
            Layout.fillWidth: true
            visible: text.length > 0
            text: root.viewModel.fieldErrors.form || root.viewModel.fieldErrors.yamlText || ""
            severity: "danger"
        }
        Components.GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: root.viewModel.currentStage
                    Flickable {
                        contentHeight: connectForm.implicitHeight
                        clip: true
                        ColumnLayout {
                            id: connectForm
                            width: parent.width
                            spacing: 10
                            Text { text: "사이트 연결"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                            Components.AppTextField { id: supplierName; Layout.fillWidth: true; placeholderText: "도매처명"; Accessible.name: "도매처명" }
                            Components.AppTextField { id: mainUrl; Layout.fillWidth: true; placeholderText: "https://example.com"; Accessible.name: "메인 URL" }
                            Components.AppTextField { id: listingUrl; Layout.fillWidth: true; placeholderText: "상품 목록 URL (선택)"; Accessible.name: "상품 목록 URL" }
                            Components.AppTextField { id: detailUrl; Layout.fillWidth: true; placeholderText: "샘플 상품 URL (선택)"; Accessible.name: "샘플 상품 URL" }
                            CheckBox { id: needsLogin; text: "로그인 필요"; Accessible.name: text }
                            Components.AppTextField { id: loginUrl; visible: needsLogin.checked; Layout.fillWidth: true; placeholderText: "로그인 URL" }
                            Components.AppTextField { id: username; visible: needsLogin.checked; Layout.fillWidth: true; placeholderText: "아이디" }
                            Components.AppTextField { id: password; visible: needsLogin.checked; Layout.fillWidth: true; placeholderText: "비밀번호"; echoMode: TextInput.Password }
                            RowLayout {
                                Components.AppButton {
                                    text: "사이트 분석"
                                    enabled: !root.viewModel.busy
                                    selected: true
                                    onClicked: {
                                        root.viewModel.setConnectionInputs({supplierName: supplierName.text, mainUrl: mainUrl.text, listingUrl: listingUrl.text, detailUrl: detailUrl.text, needsLogin: needsLogin.checked})
                                        root.viewModel.setLoginInputs({loginUrl: loginUrl.text, username: username.text, password: password.text})
                                        root.viewModel.probe()
                                        username.text = ""
                                        password.text = ""
                                    }
                                }
                                Components.AppButton { text: "취소"; enabled: root.viewModel.busy; onClicked: root.viewModel.cancelProbe() }
                            }
                        }
                    }
                    ColumnLayout {
                        Text { text: "분석 결과"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                        Text { text: "카테고리 " + (root.viewModel.probeSummary.categoryCount || 0) + "개 · " + (root.viewModel.probeSummary.encoding || "-"); color: Ui.Theme.textMuted }
                        ListView {
                            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                            model: root.viewModel.probeSummary.sampleProducts || []
                            delegate: Text { required property var modelData; width: ListView.view.width; text: modelData.name || modelData.url || ""; color: Ui.Theme.text; elide: Text.ElideRight }
                        }
                        RowLayout {
                            Components.AppButton { text: "전체상품 선택"; onClicked: root.viewModel.pickAllProducts() }
                            Components.AppButton { text: "AI 설정 생성"; selected: true; enabled: !root.viewModel.busy; onClicked: root.viewModel.generate() }
                            Components.AppButton { text: "취소"; enabled: root.viewModel.busy; onClicked: root.viewModel.cancelGenerate() }
                        }
                    }
                    ColumnLayout {
                        Text { text: "필드 매핑"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                        Components.MappingTable { Layout.fillWidth: true; Layout.fillHeight: true; model: root.viewModel.mappingRows; viewModel: root.viewModel }
                        RowLayout {
                            Components.AppButton { text: "선택 적용"; onClicked: root.viewModel.acceptPickedHint() }
                            Components.AppButton { text: "전체 테스트"; selected: true; enabled: !root.viewModel.busy; onClicked: root.viewModel.testAll() }
                        }
                    }
                    ColumnLayout {
                        Text { text: "검증 및 저장"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                        Text { text: root.viewModel.validationSummary.message || "검증이 필요합니다."; color: root.viewModel.canSave ? Ui.Theme.success : Ui.Theme.warning }
                        Text { text: "샘플 " + (root.viewModel.validationSummary.totalSamples || 0) + "개"; color: Ui.Theme.textMuted }
                        Item { Layout.fillHeight: true }
                        Components.AppButton { text: "어댑터 저장"; selected: true; enabled: root.viewModel.canSave && !root.viewModel.busy; onClicked: root.viewModel.save() }
                    }
                }
                CheckBox {
                    text: "Advanced YAML 편집"
                    checked: root.viewModel.advancedEditorOpen
                    onToggled: root.viewModel.setAdvancedEditorOpen(checked)
                }
                Components.YamlEditor {
                    visible: root.viewModel.advancedEditorOpen
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? Math.min(260, root.height * 0.35) : 0
                    viewModel: root.viewModel
                }
            }
        }
    }
}
