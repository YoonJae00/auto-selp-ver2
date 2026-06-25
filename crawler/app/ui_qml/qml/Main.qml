pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import "." as Ui
import "components"
import "screens" as Screens

ApplicationWindow {
    id: window
    objectName: "appWindow"
    width: 1180
    height: 800
    minimumWidth: 900
    minimumHeight: 620
    visible: true
    title: "Auto-Selp Crawler"
    color: Ui.Theme.canvas
    property var firstRunViewModel: null
    property var appViewModel: null
    property bool firstRunRequired: true

    Component.onCompleted: {
        // qmllint disable unqualified
        firstRunViewModel = FirstRunVM
        appViewModel = AppVM
        // qmllint enable unqualified
        firstRunRequired = firstRunViewModel && firstRunViewModel.required
    }

    Connections {
        target: window.firstRunViewModel
        function onRequiredChanged() {
            window.firstRunRequired = window.firstRunViewModel && window.firstRunViewModel.required
        }
    }

    Loader {
        anchors.fill: parent
        sourceComponent: window.firstRunRequired ? firstRunComponent : shellComponent
    }

    Component {
        id: firstRunComponent
        Screens.FirstRunScreen {
            viewModel: window.firstRunViewModel
        }
    }

    Component {
        id: shellComponent
        AppShell {
            viewModel: window.appViewModel
        }
    }
}
