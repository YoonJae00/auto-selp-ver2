pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import "../components"
import ".." as Ui

Item {
    id: root
    objectName: "exportScreen"
    required property var viewModel
    readonly property int minimumContentWidth: 620
    // 문제가 있을 때만 상세 목록을 펼친다 (필수 오류는 항상 펼침)
    property bool showIssues: false

    FileDialog {
        id: exportFileDialog
        title: "Excel 내보내기"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "xlsx"
        nameFilters: ["Excel (*.xlsx)"]
        onAccepted: root.viewModel.setOutputPath(selectedFile)
    }

    ScrollView {
        id: exportScroll
        objectName: "exportScrollView"
        anchors.fill: parent
        clip: true
        contentWidth: Math.max(root.minimumContentWidth, availableWidth)

        ColumnLayout {
            width: exportScroll.contentWidth
            spacing: 12

            // ── 무엇을 내보낼지: 도매처 선택 → 자동 검사 ──
            GlassPanel {
                Layout.fillWidth: true
                implicitHeight: exportScopeCol.implicitHeight + 32
                ColumnLayout {
                    id: exportScopeCol
                    anchors { top: parent.top; left: parent.left; right: parent.right; margins: 16 }
                    spacing: 12

                    Text { text: "어느 도매처의 상품대장을 내보낼까요?"; color: Ui.Theme.text; font.bold: true; font.pixelSize: 16 }

                    RowLayout {
                        Layout.fillWidth: true
                        ComboBox {
                            id: supplierFilter
                            objectName: "exportSupplierFilter"
                            Layout.preferredWidth: 280
                            model: root.viewModel.supplierList
                            textRole: "name"; valueRole: "id"
                            Binding on currentIndex { value: root.viewModel.selectedSupplierIndex }
                            Accessible.name: "내보낼 도매처"
                            // 도매처를 고르면 곧바로 자동 검사 — 별도 '검증' 버튼 불필요
                            onActivated: {
                                root.showIssues = false
                                root.viewModel.setSupplierId(currentValue)
                                if (currentValue)
                                    root.viewModel.validateScope()
                            }
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            visible: root.viewModel.validated
                            text: "상품 " + root.viewModel.productCount + "개 · 옵션 " + root.viewModel.optionCount + "개"
                            color: Ui.Theme.textMuted
                        }
                    }

                    // 자동 검사 결과를 한 줄로 — 개발자식 '검증' 대신 사용자 언어
                    RowLayout {
                        Layout.fillWidth: true
                        visible: root.viewModel.validated
                        StatusBadge {
                            objectName: "exportStatusBadge"
                            text: root.viewModel.blockingCount > 0
                                    ? "필수 항목 누락 " + root.viewModel.blockingCount + "건"
                                    : root.viewModel.warningCount > 0
                                        ? "권장 항목 누락 " + root.viewModel.warningCount + "건"
                                        : "모든 항목이 채워졌습니다"
                            variant: root.viewModel.blockingCount > 0 ? "danger"
                                     : root.viewModel.warningCount > 0 ? "warning" : "success"
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: root.viewModel.blockingCount > 0
                            text: "상품명·코드·상태가 빠진 상품이 있어 내보낼 수 없습니다. 수집 화면에서 다시 수집하세요."
                            color: Ui.Theme.textMuted; font.pixelSize: 12; wrapMode: Text.Wrap
                        }
                        AppButton {
                            visible: (root.viewModel.blockingCount + root.viewModel.warningCount) > 0
                            text: root.showIssues ? "접기" : "자세히"
                            onClicked: root.showIssues = !root.showIssues
                        }
                    }

                    // 문제 상세 (필요할 때만)
                    ValidationList {
                        objectName: "exportValidationList"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 180
                        visible: root.viewModel.validated && (root.showIssues || root.viewModel.blockingCount > 0)
                        model: root.viewModel.issues
                        onIssueActivated: index => root.viewModel.selectIssue(index)
                    }

                    // 경고만 있을 때: 확인하고 진행 (오류는 확인으로 넘길 수 없음)
                    CheckBox {
                        id: warningAcknowledgement
                        objectName: "exportWarningAcknowledgement"
                        visible: root.viewModel.validated && root.viewModel.warningCount > 0 && root.viewModel.blockingCount === 0
                        text: "권장 항목이 빠졌지만 이대로 내보냅니다"
                        Accessible.name: text
                        onClicked: root.viewModel.acknowledgeWarnings(checked)
                        Binding on checked { value: root.viewModel.warningAcknowledged }
                    }
                }
            }

            // ── 저장 & 내보내기 ──
            GlassPanel {
                Layout.fillWidth: true
                implicitHeight: exportSaveCol.implicitHeight + 32
                ColumnLayout {
                    id: exportSaveCol
                    anchors { top: parent.top; left: parent.left; right: parent.right; margins: 16 }
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "저장 위치"; color: Ui.Theme.textMuted; font.pixelSize: 12 }
                        Text {
                            Layout.fillWidth: true
                            text: root.viewModel.destinationName || "도매처를 선택하면 기본 위치가 정해집니다"
                            color: Ui.Theme.text; elide: Text.ElideMiddle
                        }
                        AppButton {
                            objectName: "chooseExportFileButton"
                            text: "변경"
                            enabled: root.viewModel.validated
                            onClicked: {
                                exportFileDialog.selectedFile = root.viewModel.dialogSelectedFile
                                exportFileDialog.open()
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        AppButton {
                            objectName: "startExportButton"
                            text: root.viewModel.busy ? "내보내는 중…" : "엑셀로 내보내기"
                            selected: true
                            enabled: root.viewModel.canExport
                            onClicked: root.viewModel.export()
                        }
                        Text {
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: root.viewModel.fieldErrors.form || ""
                            color: Ui.Theme.dangerForeground
                            Accessible.role: Accessible.Alert
                            wrapMode: Text.Wrap
                        }
                    }
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
