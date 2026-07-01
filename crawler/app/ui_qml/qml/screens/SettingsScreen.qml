pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import ".." as Ui

Item {
    id: root
    objectName: "settingsScreen"
    required property var viewModel
    readonly property int minimumContentWidth: 620

    ScrollView {
        id: settingsScroll
        objectName: "settingsScrollView"
        anchors.fill: parent
        clip: true
        contentWidth: Math.max(root.minimumContentWidth, availableWidth)

        ColumnLayout {
            width: settingsScroll.contentWidth
            spacing: 12

            AppTextField {
                id: searchField
                objectName: "settingsSearchField"
                Layout.fillWidth: true
                placeholderText: "설정 검색 / Search settings"
                Accessible.name: "설정 검색"
            }

            SettingsSection {
                objectName: "settingsLlmSection"
                Layout.fillWidth: true
                title: "AI 제공자"
                visible: root.viewModel.filterSections(searchField.text).some(section => section.id === "llm")

                ComboBox {
                    id: providerCombo
                    objectName: "settingsProviderCombo"
                    Layout.fillWidth: true
                    model: ["gemini", "openai"]
                    currentIndex: Math.max(0, model.indexOf(root.viewModel.llmProvider))
                    Accessible.name: "AI 제공자"
                }
                AppTextField {
                    id: geminiKey
                    objectName: "geminiApiKeyInput"
                    Layout.fillWidth: true
                    echoMode: TextInput.Password
                    placeholderText: root.viewModel.geminiKeyConfigured ? "Gemini API 키 설정됨 - 변경할 때만 입력" : "Gemini API 키"
                    Accessible.name: "Gemini API 키"
                }
                AppTextField {
                    id: openaiKey
                    objectName: "openaiApiKeyInput"
                    Layout.fillWidth: true
                    echoMode: TextInput.Password
                    placeholderText: root.viewModel.openaiKeyConfigured ? "OpenAI API 키 설정됨 - 변경할 때만 입력" : "OpenAI API 키"
                    Accessible.name: "OpenAI API 키"
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; text: "저장된 키 값은 화면에 표시하지 않습니다."; color: Ui.Theme.textMuted; wrapMode: Text.Wrap }
                    AppButton { text: "Gemini 키 삭제"; onClicked: root.viewModel.removeApiKey("gemini") }
                    AppButton { text: "OpenAI 키 삭제"; onClicked: root.viewModel.removeApiKey("openai") }
                }
            }

            SettingsSection {
                objectName: "settingsBrowserSection"
                Layout.fillWidth: true
                title: "브라우저"
                visible: root.viewModel.filterSections(searchField.text).some(section => section.id === "browser")

                ComboBox {
                    id: browserCombo
                    objectName: "settingsBrowserCombo"
                    Layout.fillWidth: true
                    model: ["msedge", "chrome", "chromium"]
                    currentIndex: Math.max(0, model.indexOf(root.viewModel.browserChannel))
                    Accessible.name: "브라우저 채널"
                }
            }

            SettingsSection {
                objectName: "settingsBehaviorSection"
                Layout.fillWidth: true
                title: "동작"
                visible: root.viewModel.filterSections(searchField.text).some(section => section.id === "behavior")

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "전체 대기(초)"; color: Ui.Theme.text }
                    SpinBox {
                        id: delaySpin
                        objectName: "settingsDelaySpin"
                        from: 0
                        to: 120
                        value: root.viewModel.globalDelaySeconds
                        Accessible.name: "전체 대기 시간"
                    }
                }
                CheckBox {
                    id: updateCheck
                    objectName: "settingsUpdateCheck"
                    text: "시작 시 업데이트 확인"
                    checked: root.viewModel.checkUpdatesOnStart
                    Accessible.name: text
                }
                CheckBox {
                    id: fallbackCheck
                    objectName: "settingsFallbackCheck"
                    text: "자동 대체 활성화"
                    checked: root.viewModel.autoFallbackEnabled
                    Accessible.name: text
                }
                CheckBox {
                    id: pickerAiCheck
                    objectName: "settingsPickerAiCheck"
                    text: "요소 선택 AI 검증 (토큰 비용 발생)"
                    checked: root.viewModel.pickerAiValidation
                    Accessible.name: text
                }
            }

            InlineBanner {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.viewModel.fieldErrors.form || root.viewModel.fieldErrors.apiKey || root.viewModel.fieldErrors.browserChannel || root.viewModel.fieldErrors.llmProvider || ""
                severity: "danger"
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton {
                    objectName: "settingsSaveButton"
                    text: "저장"
                    selected: true
                    onClicked: {
                        if (root.viewModel.save(
                            providerCombo.currentText,
                            browserCombo.currentText,
                            delaySpin.value,
                            updateCheck.checked,
                            fallbackCheck.checked,
                            pickerAiCheck.checked,
                            geminiKey.text,
                            openaiKey.text
                        )) {
                            geminiKey.text = ""
                            openaiKey.text = ""
                        }
                    }
                }
            }
        }
    }
}
