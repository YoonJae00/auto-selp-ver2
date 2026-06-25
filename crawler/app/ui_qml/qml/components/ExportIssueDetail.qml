import QtQuick
import QtQuick.Layouts
import ".." as Ui

Item {
    id: root
    required property var detail

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        Text { objectName: "exportIssueCode"; text: root.detail.code || "-"; color: Ui.Theme.text; font.pixelSize: 16; font.weight: Font.DemiBold; Layout.fillWidth: true }
        Text { text: root.detail.name || "-"; color: Ui.Theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true }
        StatusBadge { text: root.detail.severity === "error" ? "오류" : "경고"; variant: root.detail.severity === "error" ? "danger" : "warning" }
        Text { objectName: "exportIssueMessage"; text: root.detail.message || ""; color: root.detail.severity === "error" ? Ui.Theme.dangerForeground : Ui.Theme.warningForeground; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Text { text: "도매처  " + (root.detail.supplier || "-"); color: Ui.Theme.textMuted; Layout.fillWidth: true }
        Text { text: "상태  " + (root.detail.status || "-"); color: Ui.Theme.textMuted; Layout.fillWidth: true }
        Text { text: "공급가  " + Number(root.detail.price || 0).toLocaleString(Qt.locale()); color: Ui.Theme.textMuted; Layout.fillWidth: true }
        Item { Layout.fillHeight: true }
    }
}
