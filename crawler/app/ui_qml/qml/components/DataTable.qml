pragma ComponentBehavior: Bound

import QtQuick
import ".." as Ui

GlassPanel {
    id: root
    property var model: null
    property Component delegate: null
    property Component header: null
    property string accessibleName: "데이터 테이블"
    property string emptyTitle: "표시할 데이터가 없습니다"
    property string emptyDescription: "데이터가 준비되면 여기에 표시됩니다."
    property alias currentIndex: view.currentIndex
    readonly property alias count: view.count

    Accessible.name: accessibleName
    Accessible.role: Accessible.List
    clip: true

    Component {
        id: fallbackDelegate
        Rectangle {
            required property var modelData
            required property int index
            objectName: "dataTableRow_" + index
            width: ListView.view.width
            height: 36
            color: ListView.isCurrentItem ? Qt.alpha(Ui.Theme.accent, 0.12) : "transparent"
            border.color: Ui.Theme.border
            border.width: 1
            Text {
                anchors.fill: parent
                anchors.margins: 10
                text: String(parent.modelData)
                color: Ui.Theme.text
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
                font.pixelSize: 12
            }
            MouseArea {
                anchors.fill: parent
                onClicked: view.currentIndex = parent.index
            }
        }
    }

    ListView {
        id: view
        objectName: "dataTableView"
        anchors.fill: parent
        anchors.margins: 1
        model: root.model
        delegate: root.delegate || fallbackDelegate
        header: root.header
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true
        focus: true
        highlight: Rectangle {
            color: "transparent"
            border.color: Ui.Theme.accent
            border.width: 1
            radius: Ui.Theme.radiusSmall
        }
        highlightMoveDuration: Ui.Theme.motionEnabled ? Ui.Theme.motionFast : 0
    }

    EmptyState {
        anchors.centerIn: parent
        visible: view.count === 0
        title: root.emptyTitle
        description: root.emptyDescription
    }
}
