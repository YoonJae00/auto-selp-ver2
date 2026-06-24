pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"
import ".." as Ui

Item {
    id: root
    required property var viewModel
    required property var appViewModel
    readonly property int minimumContentWidth: 620

    function openScheduleDetail() {
        appViewModel.set_detail_panel_open(true)
    }

    function displayTime(value) {
        if (!value) return "-"
        return new Date(value).toLocaleString(Qt.locale(), Locale.ShortFormat)
    }

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: Math.max(root.minimumContentWidth, parent.width)
            spacing: 12

            GridLayout {
                Layout.fillWidth: true
                columns: 5
                columnSpacing: 8
                MetricCard { Layout.fillWidth: true; title: "읽지 않음"; value: root.viewModel.metrics.unread || 0; semantic: "danger" }
                MetricCard { Layout.fillWidth: true; title: "품절"; value: root.viewModel.metrics.soldOut || 0; semantic: "warning" }
                MetricCard { Layout.fillWidth: true; title: "재입고"; value: root.viewModel.metrics.restocked || 0; semantic: "success" }
                MetricCard { Layout.fillWidth: true; title: "가격 변경"; value: root.viewModel.metrics.priceChanged || 0 }
                MetricCard { Layout.fillWidth: true; title: "실패 일정"; value: root.viewModel.metrics.failedSchedules || 0; semantic: "danger" }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                ComboBox {
                    id: supplierFilter
                    objectName: "monitorSupplierFilter"
                    Layout.preferredWidth: 180
                    model: root.viewModel.suppliers
                    textRole: "name"
                    valueRole: "id"
                    Accessible.name: "도매처 필터"
                    onActivated: { root.viewModel.setSupplierFilter(currentValue); root.openScheduleDetail() }
                }
                ComboBox {
                    id: typeFilter
                    Layout.preferredWidth: 150
                    model: [
                        { text: "전체 유형", value: "" }, { text: "품절", value: "sold_out" },
                        { text: "재입고", value: "restocked" }, { text: "가격 변경", value: "price_changed" },
                        { text: "재고 변경", value: "stock_changed" }
                    ]
                    textRole: "text"
                    valueRole: "value"
                    Accessible.name: "변경 유형 필터"
                    onActivated: root.viewModel.setChangeType(currentValue)
                }
                Item { Layout.fillWidth: true }
                Text { objectName: "unreadMarkerLegend"; text: "● 굵은 글씨: 읽지 않음"; color: Ui.Theme.textMuted; font.pixelSize: 11 }
                AppButton { text: "새로고침"; onClicked: root.viewModel.refresh() }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 390
                spacing: 12

                DataTable {
                    id: eventTable
                    objectName: "monitorEventsTable"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    accessibleName: "재고 변경 이벤트"
                    model: root.viewModel.events
                    emptyTitle: "변경 이벤트가 없습니다"
                    emptyDescription: "필터를 바꾸거나 다음 재고 확인을 기다려 주세요."
                    delegate: Rectangle {
                        id: eventRow
                        required property var model
                        required property int index
                        width: ListView.view.width
                        height: 64
                        color: ListView.isCurrentItem ? Qt.alpha(Ui.Theme.accent, 0.12) : "transparent"
                        border.color: Ui.Theme.border
                        Accessible.role: Accessible.ListItem
                        Accessible.name: model.supplierName + " " + model.productName + " " + model.changeLabel + (model.acknowledged ? " 읽음" : " 읽지 않음")
                        Keys.onReturnPressed: { root.viewModel.selectChange(model.id); root.openScheduleDetail() }
                        MouseArea { anchors.fill: parent; onClicked: { eventTable.currentIndex = eventRow.index; root.viewModel.selectChange(eventRow.model.id); root.openScheduleDetail() } }
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 9; spacing: 8
                            Text { text: eventRow.model.acknowledged ? "○" : "●"; color: eventRow.model.acknowledged ? Ui.Theme.textMuted : Ui.Theme.accent; Accessible.name: eventRow.model.acknowledged ? "읽음" : "읽지 않음" }
                            ColumnLayout {
                                Layout.preferredWidth: 160; spacing: 2
                                Text { text: eventRow.model.supplierName + " · " + eventRow.model.productCode; color: Ui.Theme.text; font.bold: !eventRow.model.acknowledged; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: eventRow.model.productName; color: Ui.Theme.textMuted; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                            StatusBadge { text: eventRow.model.changeLabel; variant: eventRow.model.acknowledged ? "neutral" : "accent" }
                            Text { Layout.fillWidth: true; text: eventRow.model.previousValue + "  →  " + eventRow.model.newValue; color: Ui.Theme.text; font.bold: !eventRow.model.acknowledged; elide: Text.ElideRight }
                            Text { text: root.displayTime(eventRow.model.detectedAt); color: Ui.Theme.textMuted; font.pixelSize: 11 }
                        }
                    }
                }

            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton {
                    objectName: "ackSelectedButton"
                    property string accessibleName: "선택한 변경 읽음 처리"
                    Accessible.name: accessibleName
                    text: "선택 읽음"
                    enabled: root.viewModel.selectedChangeId.length > 0
                    onClicked: root.viewModel.acknowledgeSelected()
                }
                AppButton { text: "표시된 항목 모두 읽음"; enabled: (root.viewModel.metrics.unread || 0) > 0; onClicked: root.viewModel.acknowledgeAll() }
            }
            Text { visible: text.length > 0; text: root.viewModel.fieldErrors.form || ""; color: Ui.Theme.dangerForeground; Accessible.role: Accessible.Alert }
        }
    }
}
