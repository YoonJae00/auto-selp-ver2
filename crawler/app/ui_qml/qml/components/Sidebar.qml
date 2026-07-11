pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

GlassPanel {
    id: root
    required property var viewModel
    required property bool collapsed
    required property string currentRoute
    readonly property int animationDuration: Ui.Theme.motionEnabled ? Ui.Theme.motionNormal : 0

    objectName: "sidebar"
    radius: 0
    border.width: 0
    color: Ui.Theme.surface
    implicitWidth: collapsed ? 64 : 224

    Behavior on implicitWidth {
        NumberAnimation { duration: root.animationDuration; easing.type: Easing.OutCubic }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 6

        Text {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            text: root.collapsed ? "AS" : "AUTO-SELP"
            color: Ui.Theme.accent
            font.pixelSize: root.collapsed ? 16 : 18
            font.weight: Font.Bold
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }

        Repeater {
            model: [
                { route: "suppliers", label: "도매처", shortLabel: "몰" },
                { route: "crawl", label: "수집", shortLabel: "수" },
                { route: "monitor", label: "모니터", shortLabel: "모" },
                { route: "export", label: "내보내기", shortLabel: "내" },
                { route: "settings", label: "설정", shortLabel: "설" }
            ]
            delegate: AppButton {
                required property var modelData
                Layout.fillWidth: true
                text: root.collapsed ? modelData.shortLabel : modelData.label
                selected: root.currentRoute === modelData.route
                ToolTip.text: modelData.label
                Accessible.name: modelData.label
                onClicked: root.viewModel.navigate(modelData.route)
            }
        }

        Item { Layout.fillHeight: true }

        AppButton {
            Layout.fillWidth: true
            text: root.collapsed ? ">" : "사이드바 접기"
            ToolTip.text: root.collapsed ? "사이드바 펼치기" : "사이드바 접기"
            Accessible.name: ToolTip.text
            onClicked: root.viewModel.toggle_sidebar()
        }
    }
}
