pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

// AI 전체 자동화 탭: (idle) 접속정보 폼 → (running) 라이브 대시보드 → (done) 결과 요약.
Item {
    id: root
    required property var viewModel
    signal reviewMappingRequested()
    signal reviewValidationRequested()

    readonly property bool running: viewModel.autoRunning
    readonly property bool finished: viewModel.autoDone && !viewModel.autoRunning

    function statusColor(status) {
        if (status === "confirmed") return Ui.Theme.success
        if (status === "testing") return Ui.Theme.accent
        if (status === "retry" || status === "unresolved") return Ui.Theme.warning
        if (status === "failed") return Ui.Theme.danger
        return Ui.Theme.textMuted
    }
    function statusChipText(status, attempt, cap) {
        if (status === "testing") return "검증 중"
        if (status === "retry") return "재시도 " + attempt + "/" + cap
        if (status === "confirmed") return "확정"
        if (status === "unresolved") return "확인 필요"
        if (status === "absent") return "미제공"
        return "대기"
    }
    function formatElapsed(sec) {
        var m = Math.floor(sec / 60)
        var s = sec % 60
        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s
    }
    function feedIcon(kind) {
        if (kind === "visit") return "→"
        if (kind === "shot") return "◉"
        return "✎"
    }

    StackLayout {
        anchors.fill: parent
        currentIndex: root.running ? 1 : (root.finished ? 2 : 0)

        // ── (idle) 접속정보 폼 ─────────────────────────────────────────────
        Flickable {
            contentHeight: autoForm.implicitHeight
            clip: true
            ColumnLayout {
                id: autoForm
                width: parent.width
                spacing: 8
                Text { text: "AI 자동 설정"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                Text {
                    Layout.fillWidth: true
                    text: "AI가 사이트를 분석하고 모든 필드를 자동 매핑합니다. 로그인이나 카테고리처럼 꼭 필요한 순간에만 확인을 요청합니다."
                    color: Ui.Theme.textMuted
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
                // ponytail: 테스트용 기본값 프리필 — 배포 전 아래 text 값들 지우면 됨
                AppTextField { id: autoSupplierName; Layout.fillWidth: true; text: "mockmall"; placeholderText: "도매처명"; Accessible.name: "자동 도매처명"; size: "compact" }
                AppTextField { id: autoMainUrl; Layout.fillWidth: true; text: "http://localhost:9000/index.html"; placeholderText: "https://example.com"; Accessible.name: "자동 메인 URL"; size: "compact" }
                AppTextField { id: autoDetailUrl; Layout.fillWidth: true; text: "http://localhost:9000/detail.html?product_no=101"; placeholderText: "샘플 상품 URL (필드 매핑에 사용)"; Accessible.name: "자동 샘플 상품 URL"; size: "compact" }
                AppTextField { id: autoSoldoutUrl; Layout.fillWidth: true; placeholderText: "품절 상품 URL (권장 — 품절 감지 정확도를 높입니다)"; Accessible.name: "자동 품절 상품 URL"; size: "compact" }
                CheckBox { id: autoNeedsLogin; checked: true; text: "로그인 필요"; Accessible.name: text }
                AppTextField { id: autoLoginUrl; visible: autoNeedsLogin.checked; Layout.fillWidth: true; text: "http://localhost:9000/login.html"; placeholderText: "로그인 URL"; Accessible.name: "자동 로그인 URL"; size: "compact" }
                AppTextField { id: autoUsername; visible: autoNeedsLogin.checked; Layout.fillWidth: true; text: "test"; placeholderText: "아이디"; Accessible.name: "자동 로그인 아이디"; size: "compact" }
                AppTextField { id: autoPassword; visible: autoNeedsLogin.checked; Layout.fillWidth: true; text: "test"; placeholderText: "비밀번호"; echoMode: TextInput.Password; Accessible.name: "자동 로그인 비밀번호" }
                AppButton {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    text: "AI 자동 설정 시작"
                    selected: true
                    enabled: !root.viewModel.busy
                    onClicked: {
                        root.viewModel.setConnectionInputs({supplierName: autoSupplierName.text, mainUrl: autoMainUrl.text, soldoutUrl: autoSoldoutUrl.text, detailUrl: autoDetailUrl.text, needsLogin: autoNeedsLogin.checked})
                        root.viewModel.setLoginInputs({loginUrl: autoLoginUrl.text, username: autoUsername.text, password: autoPassword.text})
                        root.viewModel.runFullAuto()
                        autoUsername.text = ""
                        autoPassword.text = ""
                    }
                    Accessible.name: text
                    Accessible.description: "접속 정보만으로 사이트 분석부터 필드 매핑, 검증까지 자동 실행합니다."
                }
            }
        }

        // ── (running) 라이브 대시보드 ─────────────────────────────────────
        ColumnLayout {
            spacing: 10

            // 헤더: 도매처 · 경과시간 · 중단
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                ColumnLayout {
                    spacing: 2
                    Text {
                        text: root.viewModel.connectionInputs.supplierName || "자동 설정"
                        color: Ui.Theme.text
                        font.pixelSize: 17
                        font.weight: Font.Bold
                    }
                    Text {
                        text: root.viewModel.connectionInputs.mainUrl || ""
                        color: Ui.Theme.textMuted
                        font.pixelSize: 11
                        elide: Text.ElideMiddle
                        Layout.maximumWidth: 360
                    }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: root.formatElapsed(root.viewModel.autoElapsedSec)
                    color: Ui.Theme.accent
                    font.pixelSize: 18
                    font.weight: Font.DemiBold
                    font.family: "monospace"
                    Accessible.name: "경과 시간 " + text
                }
                AppButton {
                    text: "중단"
                    enabled: root.viewModel.busy
                    onClicked: root.viewModel.cancelFullAuto()
                    Accessible.name: text
                    Accessible.description: "AI 자동 설정을 중단합니다."
                }
            }
            // 얇은 전체 진행바 + 현재 작업 라벨
            ProgressBar {
                Layout.fillWidth: true
                from: 0; to: 1
                value: Math.max(0, root.viewModel.currentProgress)
                indeterminate: root.viewModel.currentProgress < 0
                background: Rectangle { implicitHeight: 4; radius: 2; color: Qt.alpha(Ui.Theme.accent, 0.15) }
                contentItem: Rectangle {
                    implicitHeight: 4; radius: 2; color: Ui.Theme.accent
                    scale: Math.max(0, root.viewModel.currentProgress)
                    transformOrigin: Item.Left
                    Behavior on scale { enabled: Ui.Theme.motionEnabled; NumberAnimation { duration: Ui.Theme.motionNormal } }
                }
            }
            Text {
                Layout.fillWidth: true
                text: root.viewModel.currentProgressLabel || "진행 중..."
                color: Ui.Theme.textMuted
                font.pixelSize: 11
                elide: Text.ElideRight
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10

                // 좌: 스테이지 타임라인
                GlassPanel {
                    Layout.preferredWidth: 170
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 10
                        Text { text: "진행 단계"; color: Ui.Theme.textMuted; font.pixelSize: 11; font.weight: Font.DemiBold }
                        Repeater {
                            model: root.viewModel.autoStages
                            delegate: RowLayout {
                                id: stageRow
                                required property var modelData
                                readonly property string st: modelData.status
                                Layout.fillWidth: true
                                spacing: 8
                                Item {
                                    implicitWidth: 16; implicitHeight: 16
                                    // 대기: 흐린 원
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 10; height: 10; radius: 5
                                        visible: stageRow.st === "pending"
                                        color: "transparent"
                                        border.color: Ui.Theme.textMuted
                                        border.width: 1
                                        opacity: 0.5
                                    }
                                    // 진행중: 펄스 도트
                                    Rectangle {
                                        id: activeDot
                                        anchors.centerIn: parent
                                        width: 10; height: 10; radius: 5
                                        visible: stageRow.st === "active"
                                        color: Ui.Theme.accent
                                        SequentialAnimation on opacity {
                                            running: stageRow.st === "active" && Ui.Theme.motionEnabled
                                            loops: Animation.Infinite
                                            NumberAnimation { from: 1.0; to: 0.25; duration: 600 }
                                            NumberAnimation { from: 0.25; to: 1.0; duration: 600 }
                                        }
                                    }
                                    Text { anchors.centerIn: parent; visible: stageRow.st === "done"; text: "✓"; color: Ui.Theme.success; font.pixelSize: 12; font.weight: Font.Bold }
                                    Text { anchors.centerIn: parent; visible: stageRow.st === "failed"; text: "✕"; color: Ui.Theme.danger; font.pixelSize: 12; font.weight: Font.Bold }
                                    Text { anchors.centerIn: parent; visible: stageRow.st === "skipped"; text: "—"; color: Ui.Theme.textMuted; font.pixelSize: 12 }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: stageRow.modelData.label
                                    color: stageRow.st === "active" ? Ui.Theme.accent
                                          : stageRow.st === "pending" ? Ui.Theme.textMuted : Ui.Theme.text
                                    font.pixelSize: 12
                                    font.weight: stageRow.st === "active" ? Font.Bold : Font.Normal
                                    elide: Text.ElideRight
                                    Accessible.name: text + " " + stageRow.st
                                }
                            }
                        }
                        Item { Layout.fillHeight: true }
                    }
                }

                // 중앙: 필드 카드 그리드
                GlassPanel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    GridView {
                        id: fieldGrid
                        anchors.fill: parent
                        anchors.margins: 10
                        clip: true
                        cellWidth: Math.max(190, Math.floor(width / Math.max(1, Math.floor(width / 210))))
                        cellHeight: 92
                        model: root.viewModel.autoFields
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        Text {
                            anchors.centerIn: parent
                            visible: fieldGrid.count === 0
                            text: "필드 매핑을 준비하는 중..."
                            color: Ui.Theme.textMuted
                            font.pixelSize: 12
                        }
                        delegate: Item {
                            id: fieldCell
                            required property string label
                            required property string status
                            required property string value
                            required property string reason
                            required property int attempt
                            required property int cap
                            width: fieldGrid.cellWidth
                            height: fieldGrid.cellHeight
                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 4
                                radius: Ui.Theme.radiusMedium
                                color: Ui.Theme.surfaceRaised
                                border.width: 1
                                border.color: (fieldCell.status === "waiting" || fieldCell.status === "absent")
                                    ? Ui.Theme.border : Qt.alpha(root.statusColor(fieldCell.status), 0.7)
                                opacity: (fieldCell.status === "waiting" || fieldCell.status === "absent") ? 0.6 : 1.0
                                Behavior on border.color { enabled: Ui.Theme.motionEnabled; ColorAnimation { duration: Ui.Theme.motionNormal } }
                                Behavior on opacity { enabled: Ui.Theme.motionEnabled; NumberAnimation { duration: Ui.Theme.motionNormal } }
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 4
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Text {
                                            Layout.fillWidth: true
                                            text: fieldCell.label
                                            color: Ui.Theme.text
                                            font.pixelSize: 12
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }
                                        Rectangle {
                                            radius: 8
                                            implicitHeight: 18
                                            implicitWidth: chipText.implicitWidth + 14
                                            color: Qt.alpha(root.statusColor(fieldCell.status), 0.15)
                                            // 검증 중 카드는 칩도 은은히 펄스
                                            SequentialAnimation on opacity {
                                                running: fieldCell.status === "testing" && Ui.Theme.motionEnabled
                                                loops: Animation.Infinite
                                                NumberAnimation { from: 1.0; to: 0.45; duration: 600 }
                                                NumberAnimation { from: 0.45; to: 1.0; duration: 600 }
                                            }
                                            Text {
                                                id: chipText
                                                anchors.centerIn: parent
                                                text: root.statusChipText(fieldCell.status, fieldCell.attempt, fieldCell.cap)
                                                color: root.statusColor(fieldCell.status)
                                                font.pixelSize: 10
                                                font.weight: Font.DemiBold
                                            }
                                            Accessible.name: fieldCell.label + " " + chipText.text
                                        }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: fieldCell.value
                                        visible: fieldCell.value.length > 0
                                        color: Ui.Theme.textMuted
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: fieldCell.reason
                                        visible: fieldCell.reason.length > 0 && fieldCell.status !== "confirmed"
                                        color: fieldCell.status === "absent" ? Ui.Theme.textMuted : Ui.Theme.warningForeground
                                        font.pixelSize: 10
                                        wrapMode: Text.Wrap
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                    }
                                    Item { Layout.fillHeight: true }
                                }
                            }
                        }
                    }
                }

                // 우: 라이브 활동 (스크린샷 + 피드)
                GlassPanel {
                    Layout.preferredWidth: 270
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8
                        Text { text: "AI가 보고 있는 화면"; color: Ui.Theme.textMuted; font.pixelSize: 11; font.weight: Font.DemiBold }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 150
                            radius: Ui.Theme.radiusSmall
                            color: Qt.alpha(Ui.Theme.border, 0.3)
                            clip: true
                            Text {
                                anchors.centerIn: parent
                                visible: root.viewModel.autoLatestShot.length === 0
                                text: "캡처 대기 중"
                                color: Ui.Theme.textMuted
                                font.pixelSize: 11
                            }
                            Image {
                                id: shotImage
                                anchors.fill: parent
                                anchors.margins: 2
                                visible: root.viewModel.autoLatestShot.length > 0
                                source: root.viewModel.autoLatestShot.length > 0 ? "file://" + root.viewModel.autoLatestShot : ""
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                                cache: false
                                Behavior on source { enabled: false }
                            }
                            MouseArea {
                                anchors.fill: parent
                                enabled: root.viewModel.autoLatestShot.length > 0
                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: shotPopup.open()
                                Accessible.name: "스크린샷 확대"
                            }
                        }
                        Text { text: "활동 피드"; color: Ui.Theme.textMuted; font.pixelSize: 11; font.weight: Font.DemiBold }
                        ListView {
                            id: feedList
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            spacing: 6
                            model: root.viewModel.autoFeed
                            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                            delegate: RowLayout {
                                id: feedRow
                                required property var modelData
                                width: feedList.width - (feedList.ScrollBar.vertical.visible ? feedList.ScrollBar.vertical.width : 0)
                                spacing: 6
                                opacity: 0
                                Component.onCompleted: opacity = 1
                                Behavior on opacity { enabled: Ui.Theme.motionEnabled; NumberAnimation { duration: Ui.Theme.motionNormal } }
                                Text {
                                    text: root.feedIcon(feedRow.modelData.kind)
                                    color: feedRow.modelData.kind === "shot" ? Ui.Theme.accent : Ui.Theme.textMuted
                                    font.pixelSize: 11
                                    Layout.alignment: Qt.AlignTop
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Text {
                                        Layout.fillWidth: true
                                        text: feedRow.modelData.text
                                        color: Ui.Theme.text
                                        font.pixelSize: 11
                                        wrapMode: Text.Wrap
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        visible: (feedRow.modelData.url || "").length > 0
                                        text: feedRow.modelData.url || ""
                                        color: Ui.Theme.textMuted
                                        font.pixelSize: 9
                                        elide: Text.ElideMiddle
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── (done) 요약 ───────────────────────────────────────────────────
        Flickable {
            contentHeight: doneCol.implicitHeight
            clip: true
            ColumnLayout {
                id: doneCol
                width: parent.width
                spacing: 10
                GlassPanel {
                    Layout.fillWidth: true
                    implicitHeight: doneBanner.implicitHeight + 32
                    color: Qt.alpha(Ui.Theme.success, 0.08)
                    border.color: Ui.Theme.success
                    ColumnLayout {
                        id: doneBanner
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 4
                        Text {
                            text: "AI 자동 설정 완료"
                            color: Ui.Theme.successForeground
                            font.pixelSize: 17
                            font.weight: Font.Bold
                        }
                        Text {
                            text: "확정 " + root.viewModel.autoConfirmedCount + "개 · 확인 필요 " + root.viewModel.autoUnresolvedFields.length + "개 · 미제공 " + root.viewModel.autoAbsentCount + "개"
                            color: Ui.Theme.text
                            font.pixelSize: 13
                            Accessible.name: text
                        }
                    }
                }
                Text {
                    visible: root.viewModel.autoUnresolvedFields.length > 0
                    text: "확인이 필요한 필드 — '직접 선택'을 누르면 브라우저에서 해당 요소를 클릭해 지정할 수 있습니다."
                    color: Ui.Theme.textMuted
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
                Repeater {
                    model: root.viewModel.autoUnresolvedFields
                    delegate: GlassPanel {
                        id: unresolvedRow
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: unresolvedBody.implicitHeight + 20
                        color: Qt.alpha(Ui.Theme.warning, 0.08)
                        border.color: Qt.alpha(Ui.Theme.warning, 0.6)
                        RowLayout {
                            id: unresolvedBody
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 8
                            Text { text: "!"; color: Ui.Theme.warningForeground; font.pixelSize: 13; font.weight: Font.Bold; Layout.alignment: Qt.AlignTop; Layout.topMargin: 1 }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2
                                Text {
                                    Layout.fillWidth: true
                                    text: unresolvedRow.modelData.label
                                    color: Ui.Theme.text
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    visible: (unresolvedRow.modelData.reason || "").length > 0
                                    text: unresolvedRow.modelData.reason || ""
                                    color: Ui.Theme.textMuted
                                    font.pixelSize: 10
                                    wrapMode: Text.Wrap
                                }
                            }
                            AppButton {
                                text: "직접 선택"
                                size: "compact"
                                Layout.alignment: Qt.AlignVCenter
                                enabled: !root.viewModel.busy
                                onClicked: root.viewModel.pickElement(unresolvedRow.modelData.path)
                                Accessible.name: unresolvedRow.modelData.label + " 직접 선택"
                                Accessible.description: "브라우저에서 이 필드의 요소를 직접 클릭해 지정합니다."
                            }
                        }
                    }
                }

                // 미제공(검증된 스킵) — 이 도매처가 제공하지 않아 검증 후 건너뛴 필드.
                // 로직 누락이 아니라 "확인하고 스킵"임을 명확히 보여준다.
                Item {
                    id: absentSection
                    property var items: (root.viewModel.autoDispositions || []).filter(
                        function (d) { return d.state === "absent" || d.state === "skipped" })
                    property bool expanded: false
                    Layout.fillWidth: true
                    visible: items.length > 0
                    implicitHeight: absentCol.implicitHeight
                    ColumnLayout {
                        id: absentCol
                        width: parent.width
                        spacing: 6
                        Text {
                            text: (absentSection.expanded ? "▾ " : "▸ ") + "미제공 " + absentSection.items.length + "개 — 이 도매처가 제공하지 않아 검증 후 건너뛴 항목"
                            color: Ui.Theme.textMuted
                            font.pixelSize: 12
                            Layout.fillWidth: true
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: absentSection.expanded = !absentSection.expanded
                            }
                            Accessible.name: text
                        }
                        Repeater {
                            model: absentSection.expanded ? absentSection.items : []
                            delegate: GlassPanel {
                                id: absentRow
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: absentBody.implicitHeight + 16
                                color: Qt.alpha(Ui.Theme.border, 0.25)
                                border.color: Qt.alpha(Ui.Theme.border, 0.5)
                                ColumnLayout {
                                    id: absentBody
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.leftMargin: 12
                                    anchors.rightMargin: 12
                                    spacing: 2
                                    Text {
                                        Layout.fillWidth: true
                                        text: absentRow.modelData.label
                                        color: Ui.Theme.textMuted
                                        font.pixelSize: 12
                                        font.weight: Font.DemiBold
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        visible: (absentRow.modelData.reason || "").length > 0
                                        text: absentRow.modelData.reason || ""
                                        color: Ui.Theme.textMuted
                                        font.pixelSize: 10
                                        wrapMode: Text.Wrap
                                    }
                                }
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    spacing: 8
                    Item { Layout.fillWidth: true }
                    AppButton {
                        text: "매핑 상세 검토"
                        enabled: !root.viewModel.busy
                        onClicked: root.reviewMappingRequested()
                        Accessible.name: text
                        Accessible.description: "수동 설정 탭의 매핑 화면에서 자동 생성된 결과를 검토합니다."
                    }
                    AppButton {
                        text: "검증 화면으로"
                        selected: true
                        enabled: !root.viewModel.busy
                        onClicked: root.reviewValidationRequested()
                        Accessible.name: text
                        Accessible.description: "수동 설정 탭의 검증 화면으로 이동해 저장을 진행합니다."
                    }
                }
            }
        }
    }

    // 스크린샷 확대 팝업
    Popup {
        id: shotPopup
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: Math.min(parent ? parent.width - 80 : 800, 960)
        height: Math.min(parent ? parent.height - 80 : 600, 720)
        modal: true
        background: Rectangle {
            color: Ui.Theme.surface
            border.color: Ui.Theme.border
            border.width: 1
            radius: Ui.Theme.radiusLarge
        }
        contentItem: Image {
            source: root.viewModel.autoLatestShot.length > 0 ? "file://" + root.viewModel.autoLatestShot : ""
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false
        }
    }
}
