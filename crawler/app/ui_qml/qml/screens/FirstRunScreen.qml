pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import ".." as Ui

Item {
    id: root
    objectName: "firstRunScreen"
    required property var viewModel

    Rectangle {
        anchors.fill: parent
        color: Ui.Theme.canvas
    }

    GlassPanel {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 560)
        height: Math.min(parent.height - 48, 430)

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14

            Text {
                Layout.fillWidth: true
                text: "Auto-Selp Crawler 시작 설정"
                color: Ui.Theme.text
                font.pixelSize: 22
                font.bold: true
                wrapMode: Text.Wrap
            }
            Text {
                Layout.fillWidth: true
                text: "처음 실행하기 전에 브라우저와 OpenAI API 키를 설정하세요. 키 값은 저장만 하고 화면에 다시 표시하지 않습니다."
                color: Ui.Theme.textMuted
                wrapMode: Text.Wrap
            }

            ComboBox {
                id: browserCombo
                objectName: "firstRunBrowserCombo"
                Layout.fillWidth: true
                model: ["msedge", "chrome", "chromium"]
                Accessible.name: "브라우저 채널"
            }
            AppTextField {
                id: apiKeyField
                objectName: "firstRunApiKeyInput"
                Layout.fillWidth: true
                echoMode: TextInput.Password
                placeholderText: "OpenAI API 키"
                Accessible.name: "OpenAI API 키"
            }
            InlineBanner {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.viewModel.fieldErrors.apiKey || root.viewModel.fieldErrors.form || root.viewModel.fieldErrors.browserChannel || ""
                severity: "danger"
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                AppButton {
                    objectName: "firstRunCancelButton"
                    text: "취소"
                    onClicked: root.viewModel.cancel()
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    objectName: "firstRunCompleteButton"
                    text: "시작하기"
                    selected: true
                    onClicked: {
                        if (root.viewModel.complete(browserCombo.currentText, apiKeyField.text)) {
                            apiKeyField.text = ""
                        }
                    }
                }
            }
        }
    }
}
