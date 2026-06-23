import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

GlassPanel {
    id: root
    required property var viewModel
    required property bool panelOpen
    readonly property var task: viewModel.activeTask
    property bool expanded: panelOpen
    readonly property int animationDuration: Ui.Theme.motionEnabled ? Ui.Theme.motionNormal : 0

    objectName: "taskPanel"
    implicitHeight: expanded ? 220 : 58
    clip: true

    Behavior on implicitHeight {
        NumberAnimation { duration: root.animationDuration; easing.type: Easing.OutCubic }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: root.task.label || "활성 작업 없음"
                color: Ui.Theme.text
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            StatusBadge {
                text: root.task.state
                variant: root.task.state === "failed" ? "danger"
                         : root.task.state === "completed" ? "success"
                         : root.task.state === "running" ? "accent" : "neutral"
            }
            AppButton {
                text: root.expanded ? "접기" : "펼치기"
                ToolTip.text: root.expanded ? "작업 패널 접기" : "작업 패널 펼치기"
                Accessible.name: ToolTip.text
                onClicked: root.viewModel.toggle_task_panel()
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.expanded
            spacing: 6
            Text {
                text: root.task.stage || "대기 중"
                color: Ui.Theme.textMuted
                font.pixelSize: 12
            }
            ProgressBar {
                Layout.fillWidth: true
                from: 0
                to: 1
                value: root.task.progress < 0 ? 0 : root.task.progress
                indeterminate: root.task.state === "running" && root.task.progress < 0
            }
            Text {
                Layout.fillWidth: true
                visible: root.task.errorMessage.length > 0
                text: root.task.errorMessage
                color: Ui.Theme.danger
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                TextArea {
                    text: root.task.logs.join("\n")
                    color: Ui.Theme.textMuted
                    readOnly: true
                    font.pixelSize: 11
                    background: null
                }
            }
        }
    }
}
