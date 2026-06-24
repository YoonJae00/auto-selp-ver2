pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import ".." as Ui

Item {
    id: root
    objectName: "exportScreen"
    required property var viewModel
    readonly property int minimumContentWidth: 620

    ScrollView {
        id: exportScroll
        objectName: "exportScrollView"
        anchors.fill: parent
        clip: true
        contentWidth: Math.max(root.minimumContentWidth, availableWidth)

        ColumnLayout {
            width: exportScroll.contentWidth
            spacing: 12

            GlassPanel {
                Layout.fillWidth: true
                Layout.preferredHeight: 104
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14
                    Text { text: "1. 범위"; color: Ui.Theme.text; font.bold: true; font.pixelSize: 16 }
                    RowLayout {
                        ComboBox {
                            id: supplierFilter
                            objectName: "exportSupplierFilter"
                            Layout.preferredWidth: 260
                            model: root.viewModel.suppliers
                            textRole: "name"; valueRole: "id"
                            Accessible.name: "내보낼 도매처"
                            onActivated: root.viewModel.setSupplierId(currentValue)
                        }
                        AppButton { objectName: "validateExportButton"; text: "검증"; enabled: !root.viewModel.busy; onClicked: root.viewModel.validateScope() }
                        Item { Layout.fillWidth: true }
                        Text { text: "상품 " + root.viewModel.productCount + " · 옵션 " + root.viewModel.optionCount; color: Ui.Theme.textMuted }
                    }
                }
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.preferredHeight: 230
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14
                    Text { text: "2. 검증"; color: Ui.Theme.text; font.bold: true; font.pixelSize: 16 }
                    ValidationList { objectName: "exportValidationList"; Layout.fillWidth: true; Layout.fillHeight: true; model: root.viewModel.issues; onIssueActivated: index => root.viewModel.selectIssue(index) }
                    CheckBox {
                        objectName: "exportWarningAcknowledgement"
                        text: "경고를 확인했으며 계속 진행합니다"
                        Accessible.name: text
                        onToggled: root.viewModel.acknowledgeWarnings(checked)
                    }
                }
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.preferredHeight: 112
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 14
                    Text { text: "3. 대상"; color: Ui.Theme.text; font.bold: true; font.pixelSize: 16 }
                    RowLayout {
                        Text { Layout.fillWidth: true; text: root.viewModel.destinationName || "저장 위치를 선택하세요"; color: Ui.Theme.text; elide: Text.ElideMiddle }
                        AppButton { objectName: "chooseExportFileButton"; text: "위치 선택"; onClicked: root.viewModel.chooseOutputFile() }
                        AppButton { objectName: "startExportButton"; text: root.viewModel.busy ? "내보내는 중" : "내보내기"; enabled: root.viewModel.canExport; onClicked: root.viewModel.export() }
                    }
                    Text { visible: text.length > 0; text: root.viewModel.fieldErrors.form || ""; color: Ui.Theme.dangerForeground; Accessible.role: Accessible.Alert }
                }
            }

            Text { text: "최근 내보내기"; color: Ui.Theme.text; font.bold: true; font.pixelSize: 16 }
            ListView {
                objectName: "exportHistoryList"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(280, contentHeight)
                model: root.viewModel.history
                reuseItems: true; clip: true; spacing: 4
                Accessible.role: Accessible.List
                Accessible.name: "최근 내보내기 기록"
                delegate: Rectangle {
                    id: historyRow
                    required property var model
                    width: ListView.view.width; height: 44
                    color: "transparent"; border.color: Ui.Theme.border
                    Accessible.role: Accessible.ListItem
                    Accessible.name: model.fileName + " " + model.outcome
                    RowLayout { anchors.fill: parent; anchors.margins: 8
                        Text { Layout.fillWidth: true; text: historyRow.model.fileName; color: Ui.Theme.text; elide: Text.ElideMiddle }
                        Text { text: historyRow.model.rowCount + "행"; color: Ui.Theme.textMuted }
                        Text { text: historyRow.model.exportedAt; color: Ui.Theme.textMuted }
                        Text { text: historyRow.model.outcome; color: historyRow.model.outcome === "success" ? Ui.Theme.successForeground : Ui.Theme.dangerForeground }
                    }
                }
            }
        }
    }
}
