import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

FocusScope {
    id: root
    required property var viewModel
    signal closeRequested()
    Accessible.role: Accessible.Dialog
    Accessible.name: viewModel.isEditing ? "도매처 편집" : "새 도매처 추가"
    Keys.onEscapePressed: event => {
        root.closeRequested()
        event.accepted = true
    }
    onVisibleChanged: {
        passwordField.clear()
        if (visible)
            Qt.callLater(function() { nameField.forceActiveFocus() })
    }

    Rectangle {
        anchors.fill: parent
        color: Ui.Theme.surfaceRaised
        border.color: Ui.Theme.border
        border.width: 1
        radius: Ui.Theme.radiusLarge
    }

    ScrollView {
        anchors.fill: parent
        anchors.margins: 20
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: root.viewModel.isEditing ? "도매처 편집" : "새 도매처 추가"
                    color: Ui.Theme.text
                    font.pixelSize: 18
                    font.weight: Font.Bold
                }
                AppButton {
                    text: "닫기"
                    onClicked: root.closeRequested()
                }
            }

            Text { text: "도매처명"; color: Ui.Theme.text; font.pixelSize: 12 }
            AppTextField {
                id: nameField
                objectName: "supplierNameField"
                Layout.fillWidth: true
                text: root.viewModel.draft.name || ""
                placeholderText: "예: 아이토픽"
                Accessible.name: "도매처명"
                onTextEdited: root.viewModel.setDraft({"name": text})
            }
            Text {
                objectName: "supplierNameError"
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.viewModel.fieldErrors.name || ""
                color: Ui.Theme.dangerForeground
                font.pixelSize: 11
            }

            Text { text: "웹사이트 URL"; color: Ui.Theme.text; font.pixelSize: 12 }
            AppTextField {
                id: urlField
                objectName: "supplierUrlField"
                Layout.fillWidth: true
                text: root.viewModel.draft.baseUrl || ""
                placeholderText: "https://www.example.com"
                Accessible.name: "웹사이트 URL"
                onTextEdited: root.viewModel.setDraft({"baseUrl": text})
            }
            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.viewModel.fieldErrors.baseUrl || ""
                color: Ui.Theme.dangerForeground
                font.pixelSize: 11
            }

            CheckBox {
                text: "로그인 필요"
                checked: Boolean(root.viewModel.draft.needsLogin)
                Accessible.name: text
                onToggled: root.viewModel.setDraft({"needsLogin": checked})
            }
            AppTextField {
                id: passwordField
                objectName: "supplierPasswordField"
                Layout.fillWidth: true
                visible: Boolean(root.viewModel.draft.needsLogin)
                text: root.viewModel.draft.username || ""
                placeholderText: "로그인 아이디"
                Accessible.name: placeholderText
                onTextEdited: root.viewModel.setDraft({"username": text})
            }
            Text {
                visible: text.length > 0
                text: root.viewModel.fieldErrors.username || ""
                color: Ui.Theme.dangerForeground
                font.pixelSize: 11
            }
            AppTextField {
                Layout.fillWidth: true
                visible: Boolean(root.viewModel.draft.needsLogin)
                echoMode: TextInput.Password
                text: ""
                placeholderText: root.viewModel.draft.credentialsConfigured
                                 ? "새 비밀번호를 입력할 때만 교체됩니다"
                                 : "로그인 비밀번호"
                Accessible.name: "로그인 비밀번호 교체"
                onTextEdited: root.viewModel.setDraft({"password": text})
            }
            Text {
                visible: text.length > 0
                text: root.viewModel.fieldErrors.password || ""
                color: Ui.Theme.dangerForeground
                font.pixelSize: 11
            }

            Text { text: "어댑터"; color: Ui.Theme.text; font.pixelSize: 12 }
            ComboBox {
                Layout.fillWidth: true
                model: [""].concat(root.viewModel.adapters)
                currentIndex: Math.max(0, model.indexOf(root.viewModel.draft.adapterFile || ""))
                displayText: currentValue || "없음"
                Accessible.name: "어댑터"
                onActivated: root.viewModel.setDraft({"adapterFile": currentValue})
            }

            RowLayout {
                Layout.fillWidth: true
                Text { text: "수집 대기(초)"; color: Ui.Theme.text; Layout.fillWidth: true }
                SpinBox {
                    from: 0; to: 60
                    value: Number(root.viewModel.draft.delaySeconds || 0)
                    Accessible.name: "수집 대기 시간"
                    onValueModified: root.viewModel.setDraft({"delaySeconds": value})
                }
            }
            CheckBox {
                text: "재고 모니터링 사용"
                checked: Boolean(root.viewModel.draft.monitorEnabled)
                Accessible.name: text
                onToggled: root.viewModel.setDraft({"monitorEnabled": checked})
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "확인 주기(시간)"; color: Ui.Theme.text; Layout.fillWidth: true }
                SpinBox {
                    from: 1; to: 168
                    value: Number(root.viewModel.draft.monitorIntervalHours || 12)
                    Accessible.name: "모니터 확인 주기"
                    onValueModified: root.viewModel.setDraft({"monitorIntervalHours": value})
                }
            }
            Text {
                visible: text.length > 0
                text: root.viewModel.fieldErrors.monitorIntervalHours || ""
                color: Ui.Theme.dangerForeground
                font.pixelSize: 11
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton { text: "취소"; onClicked: root.closeRequested() }
                AppButton {
                    text: "저장"
                    selected: true
                    onClicked: root.viewModel.saveDraft()
                }
            }
        }
    }
}
