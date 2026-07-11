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
    property string backdropPolicy: "color"

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

    // 어댑터 마법사 저장 완료 → 도매처를 자동 생성/갱신하고 도매처 화면으로 이동.
    Connections {
        // qmllint disable unqualified
        target: AdapterStudioVM
        function onSupplierSaved(slug, name, baseUrl, needsLogin) {
            SuppliersVM.upsertFromAdapter(slug, name, baseUrl, needsLogin)
            CrawlVM.refreshSuppliers()
            AppVM.navigate("suppliers")
        }
        // qmllint enable unqualified
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
