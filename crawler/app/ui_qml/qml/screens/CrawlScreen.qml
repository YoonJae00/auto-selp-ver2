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

    // 도매처 목록 새로고침은 AppShell이 "수집" 라우트 진입 시 보장한다
    // (root.viewModel이 아직 바인딩되기 전 visibleChanged가 fire되는 문제 회피).

    ScrollView {
        id: crawlScroll
        objectName: "crawlScrollView"
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

    GridLayout {
        width: crawlScroll.availableWidth
        // 카테고리 선택 섹션을 펼치면 트리가 보일 공간만큼 전체 높이를 늘린다
        // (고정 높이 그대로면 fillHeight인 트리가 0px로 눌려 안 보임).
        implicitHeight: (root.compact ? 760 : Math.max(440, crawlScroll.availableHeight))
                        + (categoryModeToggle.checked ? 260 : 0)
        columns: root.compact ? 1 : 2
        columnSpacing: 14
        rowSpacing: 14

        Components.GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: root.compact ? 360 : 260
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 8

                Text { text: "1. 도매처 선택"; color: Ui.Theme.text; font.bold: true }
                ComboBox {
                    id: supplierCombo
                    objectName: "crawlSupplierCombo"
                    Layout.fillWidth: true
                    model: root.viewModel.supplierList
                    textRole: "name"
                    valueRole: "id"
                    enabled: !root.viewModel.busy
                    Accessible.name: "도매처 선택"
                    // 모델이 비었다가 채워지면 ComboBox의 currentIndex가 -1로 남아
                    // 빈칸으로 보인다 — 항목이 생기면 첫 항목을 선택해 표시한다.
                    onCountChanged: if (count > 0 && currentIndex < 0) currentIndex = 0
                    Component.onCompleted: if (count > 0 && currentIndex < 0) currentIndex = 0
                    // 콤보에 보이는 도매처를 실제 선택으로 동기화 (모델 로드/사용자 변경 모두)
                    onCurrentValueChanged: if (currentValue) root.viewModel.selectSupplier(currentValue)
                    onActivated: root.viewModel.selectSupplier(currentValue)
                }
                Components.InlineBanner { Layout.fillWidth: true; visible: text.length > 0; text: root.viewModel.fieldErrors.supplier || ""; severity: "danger" }

                // ── 전체 수집 (기본, 대부분 사용) ──
                Components.AppButton {
                    objectName: "crawlFullStartButton"
                    Layout.fillWidth: true
                    text: root.viewModel.discovering ? "카테고리 불러오는 중…" : "전체 수집 시작"
                    selected: true
                    visible: !root.viewModel.busy
                    onClicked: root.viewModel.startFullCrawl()
                }
                Text {
                    Layout.fillWidth: true
                    text: "이 도매처의 모든 상품을 수집합니다. 대부분 이 방식을 사용하세요."
                    color: Ui.Theme.textMuted
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: Ui.Theme.border }

                // ── 특정 카테고리만 수집 (고급, 접힘) ──
                CheckBox {
                    id: categoryModeToggle
                    objectName: "crawlCategoryModeToggle"
                    text: "특정 카테고리만 골라 수집"
                    enabled: !root.viewModel.busy
                    Accessible.name: text
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: categoryModeToggle.checked
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        Components.AppButton {
                            text: root.viewModel.discovering ? "불러오는 중" : "카테고리 불러오기"
                            enabled: !root.viewModel.busy
                            onClicked: root.viewModel.discoverCategories()
                        }
                        Components.AppButton { text: "전체 선택"; enabled: !root.viewModel.busy; onClicked: root.viewModel.selectAll() }
                        Components.AppButton { text: "선택 해제"; enabled: !root.viewModel.busy; onClicked: root.viewModel.clearSelection() }
                        Item { Layout.fillWidth: true }
                        Text { text: root.viewModel.selectedCategoryIds.length + "개 선택"; color: Ui.Theme.textMuted }
                    }
                    Components.CategoryTree { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 220; viewModel: root.viewModel }
                    Components.InlineBanner { Layout.fillWidth: true; visible: text.length > 0; text: root.viewModel.fieldErrors.categories || ""; severity: "danger" }
                    Components.AppButton {
                        objectName: "crawlStartButton"
                        Layout.fillWidth: true
                        text: "선택 카테고리 수집 시작"
                        visible: !root.viewModel.busy
                        onClicked: root.viewModel.startCrawl()
                    }
                }
            }
        }

        Components.GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: root.compact ? 360 : 260
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10
                Text { text: "2. 진행 상황"; color: Ui.Theme.text; font.bold: true }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "최대 페이지"; color: Ui.Theme.text }
                    SpinBox { value: root.viewModel.maxPages; from: 1; to: 500; enabled: !root.viewModel.busy; Accessible.name: "최대 페이지"; onValueModified: root.viewModel.setMaxPages(value) }
                    Label { text: "대기(초)"; color: Ui.Theme.text }
                    SpinBox { value: root.viewModel.delaySeconds; from: -1; to: 60; enabled: !root.viewModel.busy; Accessible.name: "대기 시간"; textFromValue: function(value) { return value < 0 ? "자동" : value.toString() }; onValueModified: root.viewModel.setDelaySeconds(value) }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Components.AppButton { objectName: "crawlRecrawlButton"; text: "다시 수집하기"; visible: !root.viewModel.busy; onClicked: root.viewModel.startRecrawl() }
                    Components.AppButton { objectName: "crawlCancelButton"; text: "취소"; visible: root.viewModel.busy; onClicked: root.viewModel.cancelCrawl() }
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
}
