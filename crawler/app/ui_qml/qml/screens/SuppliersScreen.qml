pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui
import "../components" as Components

Item {
    id: root
    required property var viewModel
    readonly property bool wideEditor: Window.window ? Window.window.width >= 1040 : width >= 1040
    focus: true

    RowLayout {
        anchors.fill: parent
        spacing: 14

        Components.GlassPanel {
            Layout.fillHeight: true
            Layout.preferredWidth: 270
            Layout.minimumWidth: 220

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: "도매처"
                        color: Ui.Theme.text
                        font.pixelSize: 16
                        font.weight: Font.Bold
                    }
                    Components.AppButton {
                        objectName: "addSupplierButton"
                        text: "+ 추가"
                        selected: true
                        onClicked: root.viewModel.beginCreate()
                    }
                }
                ListView {
                    id: supplierList
                    objectName: "supplierList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: root.viewModel.model
                    spacing: 4
                    activeFocusOnTab: true
                    Accessible.name: "도매처 목록"
                    delegate: Item {
                        id: supplierRow
                        required property string id
                        required property string name
                        required property string baseUrl
                        required property bool needsLogin
                        required property bool credentialsConfigured
                        required property bool adapterReady
                        required property bool monitorEnabled
                        required property string lastCrawlAt
                        width: ListView.view.width
                        height: supplierDelegate.implicitHeight
                        ItemDelegate {
                            id: supplierDelegate
                            width: parent.width
                            highlighted: supplierRow.id === root.viewModel.selectedId
                            Accessible.name: supplierRow.name
                            onClicked: root.viewModel.selectSupplier(supplierRow.id)
                            contentItem: Column {
                                spacing: 3
                                Text {
                                    text: supplierRow.name
                                    color: Ui.Theme.text
                                    font.weight: Font.DemiBold
                                }
                                Text {
                                    width: parent.width
                                    text: supplierRow.baseUrl
                                    color: Ui.Theme.textMuted
                                    elide: Text.ElideRight
                                    font.pixelSize: 11
                                }
                                Flow {
                                    width: parent.width
                                    spacing: 4
                                    Components.StatusBadge {
                                        objectName: "supplierLoginStatus"
                                        text: !supplierRow.needsLogin ? "로그인 불필요"
                                              : supplierRow.credentialsConfigured ? "로그인 저장됨"
                                              : "로그인 미설정"
                                        variant: supplierRow.needsLogin
                                                 && !supplierRow.credentialsConfigured
                                                 ? "warning" : "neutral"
                                    }
                                    Components.StatusBadge {
                                        objectName: "supplierAdapterStatus"
                                        text: supplierRow.adapterReady ? "어댑터 준비됨" : "어댑터 없음"
                                        variant: supplierRow.adapterReady ? "success" : "warning"
                                    }
                                    Components.StatusBadge {
                                        objectName: "supplierMonitorStatus"
                                        text: supplierRow.monitorEnabled ? "모니터링 사용" : "모니터링 미사용"
                                        variant: supplierRow.monitorEnabled ? "success" : "neutral"
                                    }
                                    Components.StatusBadge {
                                        objectName: "supplierLastCrawlStatus"
                                        text: supplierRow.lastCrawlAt
                                              ? "최근 수집 " + supplierRow.lastCrawlAt
                                              : "수집 기록 없음"
                                        variant: "neutral"
                                    }
                                }
                            }
                        }
                    }
                }
                Components.EmptyState {
                    visible: supplierList.count === 0
                    Layout.alignment: Qt.AlignCenter
                    title: "등록된 도매처가 없습니다"
                    description: "+ 추가 버튼으로 시작하세요."
                }
            }
        }

        Components.GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Components.EmptyState {
                anchors.centerIn: parent
                visible: !root.viewModel.selectedId
                title: "도매처를 선택하세요"
                description: "왼쪽 목록에서 상세 정보를 확인할 도매처를 선택하세요."
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 22
                visible: Boolean(root.viewModel.selectedId)
                spacing: 14
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: root.viewModel.selectedSupplier.name || ""
                        color: Ui.Theme.text
                        font.pixelSize: 22
                        font.weight: Font.Bold
                    }
                    Components.AppButton { text: "편집"; onClicked: root.viewModel.beginEdit() }
                    Components.AppButton { text: "삭제"; onClicked: root.viewModel.requestDelete() }
                }
                Text {
                    Layout.fillWidth: true
                    text: root.viewModel.selectedSupplier.baseUrl || ""
                    color: Ui.Theme.accent
                    wrapMode: Text.WrapAnywhere
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    Components.StatusBadge {
                        text: root.viewModel.selectedSupplier.adapterReady ? "어댑터 준비됨" : "어댑터 없음"
                        variant: root.viewModel.selectedSupplier.adapterReady ? "success" : "warning"
                    }
                    Components.StatusBadge {
                        text: root.viewModel.selectedSupplier.monitorEnabled ? "모니터링 사용" : "모니터링 미사용"
                        variant: root.viewModel.selectedSupplier.monitorEnabled ? "success" : "neutral"
                    }
                    Components.StatusBadge {
                        text: root.viewModel.selectedSupplier.credentialsConfigured ? "로그인 정보 저장됨" : "로그인 정보 없음"
                        variant: root.viewModel.selectedSupplier.credentialsConfigured ? "success" : "neutral"
                    }
                }
                Text {
                    text: "어댑터: " + (root.viewModel.selectedSupplier.adapterFile || "없음")
                    color: Ui.Theme.text
                }
                Text {
                    text: "수집 대기: " + (root.viewModel.selectedSupplier.delaySeconds
                                        ? root.viewModel.selectedSupplier.delaySeconds + "초" : "전역 설정")
                    color: Ui.Theme.text
                }
                Text {
                    text: "모니터 확인 주기: " + (root.viewModel.selectedSupplier.monitorIntervalHours || 12) + "시간"
                    color: Ui.Theme.text
                }
                Text {
                    text: "마지막 수집: " + (root.viewModel.selectedSupplier.lastCrawlAt || "기록 없음")
                    color: Ui.Theme.textMuted
                }
                Item { Layout.fillHeight: true }
            }
        }

        Components.SupplierEditor {
            objectName: "supplierEditor"
            viewModel: root.viewModel
            visible: root.viewModel.editorOpen && root.wideEditor
            Layout.fillHeight: true
            Layout.preferredWidth: visible ? 380 : 0
            Layout.minimumWidth: visible ? 340 : 0
            onCloseRequested: root.viewModel.cancelEdit()
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: root.viewModel.editorOpen && !root.wideEditor
        color: "#66000000"
        z: 9
        MouseArea { anchors.fill: parent; onClicked: root.viewModel.cancelEdit() }
    }
    Components.SupplierEditor {
        objectName: "supplierEditorOverlay"
        viewModel: root.viewModel
        visible: root.viewModel.editorOpen && !root.wideEditor
        width: Math.min(420, parent.width * 0.9)
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        z: 10
        onCloseRequested: root.viewModel.cancelEdit()
    }

    Components.ConfirmDialog {
        id: deleteDialog
        objectName: "supplierDeleteDialog"
        anchors.centerIn: parent
        message: "이 도매처와 관련된 모든 상품 데이터를 삭제합니다. 계속하시겠습니까?"
        onConfirmed: root.viewModel.confirmDelete()
        onRejected: root.viewModel.cancelDelete()
    }
    Connections {
        target: root.viewModel
        function onDeleteConfirmationChanged() {
            if (root.viewModel.deleteConfirmationOpen)
                deleteDialog.open()
            else
                deleteDialog.close()
        }
    }
}
