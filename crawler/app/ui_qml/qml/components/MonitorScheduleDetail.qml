import QtQuick
import QtQuick.Layouts
import ".." as Ui

Item {
    id: root
    required property var schedule

    function displayTime(value) {
        return value ? new Date(value).toLocaleString(Qt.locale(), Locale.ShortFormat) : "-"
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        Text { text: root.schedule.supplierName || "도매처를 선택하세요"; color: Ui.Theme.text; font.pixelSize: 15; font.weight: Font.DemiBold; wrapMode: Text.Wrap; Layout.fillWidth: true }
        StatusBadge { text: root.schedule.monitorEnabled ? "모니터링 사용" : "모니터링 중지"; variant: root.schedule.monitorEnabled ? "success" : "neutral" }
        Text { text: "주기  " + (root.schedule.intervalHours || "-") + "시간"; color: Ui.Theme.textMuted }
        Text { objectName: "monitorLastCheckText"; text: "마지막 확인\n" + root.displayTime(root.schedule.lastCheckAt); color: Ui.Theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Text { objectName: "monitorNextCheckText"; text: (root.schedule.nextCheckEstimated ? "예상 다음 확인\n" : "다음 확인\n") + root.displayTime(root.schedule.nextCheckAt); color: Ui.Theme.text; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Text { objectName: "monitorFailureText"; text: root.schedule.latestFailure ? "최근 실패\n" + root.schedule.latestFailure : "최근 실패 없음"; color: root.schedule.latestFailure ? Ui.Theme.dangerForeground : Ui.Theme.textMuted; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Item { Layout.fillHeight: true }
    }
}
