import QtQuick
import QtQuick.Layouts

Item {
    id: root
    required property var viewModel
    property string currentRoute: "suppliers"
    property bool sidebarCollapsed: false
    property bool taskPanelOpen: false
    property bool detailPanelOpen: false
    readonly property bool wideDetailMode: width >= 1040
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
            objectName: "centralContent"
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

        DetailDrawer {
            objectName: "detailDrawerWide"
            modal: false
            visible: root.detailPanelOpen && root.wideDetailMode
            Layout.fillHeight: true
            Layout.preferredWidth: 320
            Layout.minimumWidth: 320
            Layout.maximumWidth: 320
            onCloseRequested: root.viewModel.set_detail_panel_open(false)
        }
    }

    Rectangle {
        objectName: "detailScrim"
        anchors.fill: parent
        visible: root.detailPanelOpen && !root.wideDetailMode
        color: "#66000000"
        z: 9
        MouseArea {
            anchors.fill: parent
            onClicked: root.viewModel.set_detail_panel_open(false)
        }
    }

    DetailDrawer {
        objectName: "detailDrawerOverlay"
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        modal: true
        visible: root.detailPanelOpen && !root.wideDetailMode
        z: 10
        onCloseRequested: root.viewModel.set_detail_panel_open(false)
    }

    ToastHost {
        anchors.fill: parent
        anchors.margins: 20
        z: 20
    }
}
