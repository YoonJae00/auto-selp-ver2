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
            width: ListView.view.width
            height: 36
            color: "transparent"
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
        }
    }

    ListView {
        id: view
        anchors.fill: parent
        anchors.margins: 1
        model: root.model
        delegate: root.delegate || fallbackDelegate
        header: root.header
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: true
        focus: true
    }

    EmptyState {
        anchors.centerIn: parent
        visible: view.count === 0
        title: root.emptyTitle
        description: root.emptyDescription
    }
}
