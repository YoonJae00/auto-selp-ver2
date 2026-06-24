pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui
import "../components" as Components

Item {
    id: root
    required property var viewModel
    readonly property bool compact: width < 760
    focus: true

    GridLayout {
        anchors.fill: parent
        columns: root.compact ? 1 : 2
        columnSpacing: 14
        rowSpacing: 14

        Components.GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 260
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 8
                Text { text: "1. 도매처와 카테고리"; color: Ui.Theme.text; font.bold: true }
                RowLayout {
                    Layout.fillWidth: true
                    ComboBox {
                        id: supplierCombo
                        objectName: "crawlSupplierCombo"
                        Layout.fillWidth: true
                        model: root.viewModel.suppliers
                        textRole: "name"
                        enabled: !root.viewModel.busy
                        Accessible.name: "도매처 선택"
                        onActivated: root.viewModel.selectSupplier(currentValue)
                        valueRole: "id"
                    }
                    Components.AppButton {
                        text: root.viewModel.discovering ? "불러오는 중" : "카테고리 불러오기"
                        enabled: !root.viewModel.busy
                        onClicked: root.viewModel.discoverCategories()
                    }
                }
                Components.InlineBanner { Layout.fillWidth: true; visible: text.length > 0; text: root.viewModel.fieldErrors.supplier || ""; severity: "danger" }
                RowLayout {
                    Layout.fillWidth: true
                    Components.AppButton { text: "전체 선택"; enabled: !root.viewModel.busy; onClicked: root.viewModel.selectAll() }
                    Components.AppButton { text: "선택 해제"; enabled: !root.viewModel.busy; onClicked: root.viewModel.clearSelection() }
                    Item { Layout.fillWidth: true }
                    Text { text: root.viewModel.selectedCategoryIds.length + "개 선택"; color: Ui.Theme.textMuted }
                }
                Components.CategoryTree { Layout.fillWidth: true; Layout.fillHeight: true; viewModel: root.viewModel }
                Components.InlineBanner { Layout.fillWidth: true; visible: text.length > 0; text: root.viewModel.fieldErrors.categories || ""; severity: "danger" }
            }
        }

        Components.GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 260
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10
                Text { text: "2. 검토 후 실행"; color: Ui.Theme.text; font.bold: true }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "최대 페이지"; color: Ui.Theme.text }
                    SpinBox { value: root.viewModel.maxPages; from: 1; to: 500; enabled: !root.viewModel.busy; Accessible.name: "최대 페이지"; onValueModified: root.viewModel.setMaxPages(value) }
                    Label { text: "대기(초)"; color: Ui.Theme.text }
                    SpinBox { value: root.viewModel.delaySeconds; from: -1; to: 60; enabled: !root.viewModel.busy; Accessible.name: "대기 시간"; textFromValue: function(value) { return value < 0 ? "자동" : value.toString() }; onValueModified: root.viewModel.setDelaySeconds(value) }
                }
                Text {
                    Layout.fillWidth: true
                    text: "선택 카테고리 " + root.viewModel.selectedCategoryIds.length + "개 · 카테고리당 최대 " + root.viewModel.maxPages + "페이지"
                    color: Ui.Theme.textMuted
                    wrapMode: Text.Wrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    Components.AppButton { text: "수집 시작"; selected: true; enabled: !root.viewModel.busy; onClicked: root.viewModel.startCrawl() }
                    Components.AppButton { text: "취소"; enabled: root.viewModel.busy; onClicked: root.viewModel.cancelCrawl() }
                    Item { Layout.fillWidth: true }
                    Text { text: root.viewModel.elapsedSeconds + "초"; color: Ui.Theme.textMuted }
                }
                Components.InlineBanner { Layout.fillWidth: true; visible: text.length > 0; text: root.viewModel.fieldErrors.form || root.viewModel.fieldErrors.maxPages || root.viewModel.fieldErrors.delaySeconds || ""; severity: "danger" }
                Text { Layout.fillWidth: true; text: root.viewModel.currentTarget || "대기 중"; color: Ui.Theme.text; elide: Text.ElideMiddle }
                Text { text: "상품 " + root.viewModel.productCount + "개 · 옵션 " + root.viewModel.optionCount + "개"; color: Ui.Theme.accent; font.bold: true }
                Components.CrawlResults { Layout.fillWidth: true; Layout.fillHeight: true; viewModel: root.viewModel }
            }
        }
    }
}
