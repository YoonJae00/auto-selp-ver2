import QtQuick
import QtQuick.Controls.Basic
import "." as Ui
import "components"

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

    AppShell {
        anchors.fill: parent
        // qmllint disable unqualified
        viewModel: AppVM
        // qmllint enable unqualified
    }
}
