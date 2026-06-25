import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

FocusScope {
    id: root
    property string title: "상세 정보"
    property bool modal: false
    property Item previousFocusItem: null
    property Component contentComponent: null
    signal closeRequested()

    width: Math.min(340, parent ? parent.width * 0.86 : 340)
    Accessible.role: Accessible.Dialog
    Accessible.name: title
    Keys.onEscapePressed: event => {
        if (root.modal) {
            root.closeRequested()
            event.accepted = true
        }
    }

    onVisibleChanged: {
        if (visible && modal) {
            previousFocusItem = Window.window ? Window.window.activeFocusItem : null
            root.forceActiveFocus(Qt.PopupFocusReason)
            Qt.callLater(function() { closeButton.forceActiveFocus() })
        } else if (!visible && previousFocusItem) {
            previousFocusItem.forceActiveFocus()
            previousFocusItem = null
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Ui.Theme.surfaceRaised
        border.color: Ui.Theme.border
        border.width: 1
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: root.title
                color: Ui.Theme.text
                font.pixelSize: 18
                font.weight: Font.Bold
            }
            AppButton {
                id: closeButton
                objectName: "drawerCloseButton"
                text: "닫기"
                ToolTip.text: "상세 패널 닫기"
                Accessible.name: ToolTip.text
                KeyNavigation.priority: KeyNavigation.BeforeItem
                KeyNavigation.tab: root.modal ? closeButton : null
                KeyNavigation.backtab: root.modal ? closeButton : null
                onClicked: root.closeRequested()
            }
        }
        Loader {
            Layout.fillWidth: true
            Layout.fillHeight: true
            sourceComponent: root.contentComponent || defaultContent
        }
    }

    Component {
        id: defaultContent
        Item {
            Text {
                anchors.top: parent.top
                width: parent.width
                text: "선택한 항목의 상세 정보가 여기에 표시됩니다."
                color: Ui.Theme.textMuted
                wrapMode: Text.Wrap
                font.pixelSize: 13
            }
        }
    }
}
