import QtQuick
import QtQuick.Layouts
import ".." as Ui

Item {
    id: root
    required property var viewModel
    property string currentRoute: "suppliers"
    property bool sidebarCollapsed: false
    property bool taskPanelOpen: false
    property bool detailPanelOpen: false
    readonly property var routes: ["suppliers", "adapter", "crawl", "monitor", "export", "settings"]
    readonly property int routeIndex: Math.max(0, routes.indexOf(currentRoute))

    function syncViewModel() {
        currentRoute = viewModel.currentRoute
        sidebarCollapsed = viewModel.sidebarCollapsed
        taskPanelOpen = viewModel.taskPanelOpen
        detailPanelOpen = viewModel.detailPanelOpen
    }

    Component.onCompleted: syncViewModel()
    Connections {
        target: root.viewModel
        function onChanged() { root.syncViewModel() }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            viewModel: root.viewModel
            collapsed: root.sidebarCollapsed
            currentRoute: root.currentRoute
            Layout.fillHeight: true
            Layout.preferredWidth: implicitWidth
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 20
            spacing: 14

            ContentHeader {
                Layout.fillWidth: true
                route: root.currentRoute
            }

            StackLayout {
                objectName: "contentStack"
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.routeIndex

                PlaceholderScreen { title: "공급사" }
                PlaceholderScreen { title: "어댑터" }
                PlaceholderScreen { title: "수집" }
                PlaceholderScreen { title: "모니터" }
                PlaceholderScreen { title: "내보내기" }
                PlaceholderScreen { title: "설정" }
            }

            TaskPanel {
                viewModel: root.viewModel
                panelOpen: root.taskPanelOpen
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
            }
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: root.detailPanelOpen && root.width < 900
        color: "#66000000"
        z: 9
    }

    DetailDrawer {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: root.detailPanelOpen
        z: 10
    }

    ToastHost {
        anchors.fill: parent
        anchors.margins: 20
        z: 20
    }
}
