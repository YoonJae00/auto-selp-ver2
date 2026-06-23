import QtQuick
import QtQuick.Layouts
import ".." as Ui

Item {
    id: root
    property string route: "suppliers"
    readonly property var routeCopy: ({
        suppliers: ["공급사", "공급사 연결과 상태를 관리합니다."],
        adapter: ["어댑터", "사이트별 수집 규칙을 구성합니다."],
        crawl: ["수집", "상품 수집 작업을 시작합니다."],
        monitor: ["모니터", "실행 중인 작업과 기록을 확인합니다."],
        export: ["내보내기", "수집 결과를 원하는 형식으로 저장합니다."],
        settings: ["설정", "애플리케이션 환경을 관리합니다."]
    })

    implicitHeight: 72
    ColumnLayout {
        anchors.fill: parent
        spacing: 4
        Text {
            text: (root.routeCopy[root.route] || [root.route, ""])[0]
            color: Ui.Theme.text
            font.pixelSize: 24
            font.weight: Font.Bold
        }
        Text {
            text: (root.routeCopy[root.route] || [root.route, ""])[1]
            color: Ui.Theme.textMuted
            font.pixelSize: 13
        }
    }
}
