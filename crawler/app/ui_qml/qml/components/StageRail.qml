pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

Item {
    id: root
    property int currentStage: 0
    signal stageRequested(int stage)
    implicitHeight: rail.implicitHeight
    readonly property var labels: ["연결", "분석", "매핑", "검증"]

    RowLayout {
        id: rail
        anchors.fill: parent
        spacing: 8
        Repeater {
            model: 4
            delegate: Button {
                id: stageButton
                required property int index
                Layout.fillWidth: true
                text: (index + 1) + ". " + root.labels[index]
                Accessible.name: text
                onClicked: root.stageRequested(index)
                contentItem: Text {
                    text: stageButton.text
                    color: stageButton.index <= root.currentStage ? Ui.Theme.accent : Ui.Theme.textMuted
                    horizontalAlignment: Text.AlignHCenter
                    font.weight: stageButton.index === root.currentStage ? Font.Bold : Font.Normal
                }
                background: Rectangle {
                    radius: 8
                    color: stageButton.index === root.currentStage ? Ui.Theme.surfaceRaised : "transparent"
                    border.color: stageButton.index <= root.currentStage ? Ui.Theme.accent : Ui.Theme.border
                }
            }
        }
    }
}
