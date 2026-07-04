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
    implicitHeight: expanded ? 190 : 42
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
            spacing: 8
            Text {
                text: "실행 로그"
                color: Ui.Theme.text
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Text {
                Layout.fillWidth: true
                text: root.task.label || "대기 중"
                color: Ui.Theme.textMuted
                font.pixelSize: 11
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            StatusBadge {
                visible: root.task.state.length > 0 && root.task.state !== "idle"
                text: root.task.state
                variant: root.task.state === "failed" ? "danger"
                         : root.task.state === "completed" ? "success"
                         : root.task.state === "running" ? "accent" : "neutral"
            }
            AppButton {
                size: "compact"
                text: root.expanded ? "접기" : "펼치기"
                ToolTip.text: root.expanded ? "로그 접기" : "로그 펼치기"
                Accessible.name: ToolTip.text
                onClicked: root.viewModel.toggle_task_panel()
            }
        }

        // 진행 중일 때만 얇은 진행바
        ProgressBar {
            Layout.fillWidth: true
            visible: root.expanded && root.task.state === "running"
            from: 0
            to: 1
            value: root.task.progress < 0 ? 0 : root.task.progress
            indeterminate: root.task.progress < 0
        }
        Text {
            Layout.fillWidth: true
            visible: root.expanded && root.task.errorMessage.length > 0
            text: root.task.errorMessage
            color: Ui.Theme.danger
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        // 로그 본문이 대부분을 차지
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.expanded
            TextArea {
                objectName: "taskLogView"
                text: root.task.logs.join("\n")
                color: Ui.Theme.textMuted
                readOnly: true
                font.pixelSize: 11
                font.family: "monospace"
                background: null
                onTextChanged: cursorPosition = length
            }
        }
    }
}
