import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

ColumnLayout {
    id: root
    required property var viewModel
    spacing: 7
    RowLayout {
        Layout.fillWidth: true
        Text { Layout.fillWidth: true; text: "YAML 고급 편집"; color: Ui.Theme.text; font.weight: Font.Bold }
        Text {
            text: root.viewModel.validationStale ? "검증 만료" : root.viewModel.yamlDirty ? "저장되지 않음" : "저장됨"
            color: root.viewModel.validationStale ? Ui.Theme.warning : Ui.Theme.textMuted
        }
    }
    TextArea {
        Layout.fillWidth: true
        Layout.fillHeight: true
        text: root.viewModel.yamlText
        font.family: "monospace"
        wrapMode: TextEdit.NoWrap
        Accessible.name: "어댑터 YAML 편집기"
        onTextChanged: if (activeFocus && text !== root.viewModel.yamlText) root.viewModel.setYamlText(text)
        background: Rectangle { color: Ui.Theme.surface; border.color: Ui.Theme.border; radius: 8 }
        color: Ui.Theme.text
        selectionColor: Ui.Theme.accent
    }
}
