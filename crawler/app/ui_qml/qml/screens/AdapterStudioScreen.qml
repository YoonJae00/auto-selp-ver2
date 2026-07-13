pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui
import "../components" as Components

Item {
    id: root
    required property var viewModel
    property var toastHost: null
    // 0 = AI 자동 설정 (기본), 1 = 수동 설정 (기존 4단계 마법사)
    property int mode: 0
    focus: true

    ColumnLayout {
        anchors.fill: parent
        spacing: 12
        // 모드 탭
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Components.AppButton {
                text: "AI 자동 설정"
                selected: root.mode === 0
                onClicked: root.mode = 0
                Accessible.name: text
                Accessible.description: "접속 정보만 입력하면 AI가 모든 필드를 자동으로 매핑합니다."
            }
            Components.AppButton {
                text: "수동 설정"
                selected: root.mode === 1
                onClicked: root.mode = 1
                Accessible.name: text
                Accessible.description: "4단계 마법사로 직접 분석·매핑·검증을 진행합니다."
            }
            Item { Layout.fillWidth: true }
        }
        Components.InlineBanner {
            Layout.fillWidth: true
            visible: text.length > 0
            text: root.viewModel.fieldErrors.form || root.viewModel.fieldErrors.yamlText || root.viewModel.fieldErrors.detailUrl || root.viewModel.fieldErrors.soldoutUrl || ""
            severity: "danger"
        }
        // 전역 오버레이 — 두 탭 공통 (자동 실행 중에도 수동 로그인/픽커 안내가 떠야 함)
        Components.InlineBanner {
            Layout.fillWidth: true
            visible: root.viewModel.pickerActive
            text: "브라우저에서 요소를 클릭하세요 — 「" + root.viewModel.pickerFieldLabel + "」 선택 중"
            severity: "accent"
        }
        Components.GlassPanel {
            Layout.fillWidth: true
            visible: root.viewModel.manualLoginPending
            color: Qt.alpha(Ui.Theme.warning, 0.10)
            border.color: Ui.Theme.warning
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 8
                Text { text: "수동 로그인 필요"; color: Ui.Theme.warning; font.pixelSize: 13; font.weight: Font.DemiBold }
                Text {
                    Layout.fillWidth: true
                    text: "자동 로그인에 실패했습니다. 브라우저 창에서 직접 아이디와 비밀번호를 입력해 로그인한 뒤, 아래 '로그인 완료' 버튼을 누르세요. 로그인하면 요소 선택이 계속 진행됩니다."
                    color: Ui.Theme.textMuted
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Item { Layout.fillWidth: true }
                    Components.AppButton {
                        text: "취소"
                        enabled: !root.viewModel.busy
                        onClicked: root.viewModel.cancelManualLogin()
                        Accessible.name: text
                        Accessible.description: "수동 로그인을 취소하고 요소 선택을 중단합니다."
                        Accessible.role: Accessible.Button
                    }
                    Components.AppButton {
                        text: "로그인 완료"
                        selected: true
                        enabled: !root.viewModel.busy
                        onClicked: root.viewModel.confirmManualLogin()
                        Accessible.name: text
                        Accessible.description: "브라우저에서 직접 로그인을 마친 뒤 누르면 요소 선택을 계속 진행합니다."
                        Accessible.role: Accessible.Button
                    }
                }
            }
        }
        // ── 자동 탭: AI 전체 자동화 대시보드 ──
        Components.AutoAdapterDashboard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.mode === 0
            viewModel: root.viewModel
            onReviewMappingRequested: { root.viewModel.setCurrentStage(2); root.mode = 1 }
            onReviewValidationRequested: { root.viewModel.setCurrentStage(3); root.mode = 1 }
        }
        // ── 수동 탭: 기존 4단계 마법사 ──
        Components.StageRail {
            Layout.fillWidth: true
            visible: root.mode === 1
            enabled: !root.viewModel.busy
            currentStage: root.viewModel.currentStage
            onStageRequested: stage => root.viewModel.setCurrentStage(stage)
        }
        Components.GlassPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.mode === 1
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    visible: root.viewModel.busy && !root.viewModel.pickerActive
                    spacing: 6
                    Text {
                        Layout.fillWidth: true
                        text: root.viewModel.currentProgressLabel || "처리 중..."
                        color: Ui.Theme.textMuted
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    ProgressBar {
                        Layout.fillWidth: true
                        from: 0
                        to: 1
                        value: Math.max(0, root.viewModel.currentProgress)
                        indeterminate: root.viewModel.currentProgress < 0
                        background: Rectangle {
                            implicitHeight: 6
                            radius: 3
                            color: Qt.alpha(Ui.Theme.accent, 0.15)
                        }
                        contentItem: Rectangle {
                            implicitHeight: 6
                            radius: 3
                            color: Ui.Theme.accent
                            scale: Math.max(0, root.viewModel.currentProgress)
                            transformOrigin: Item.Left
                        }
                    }
                }
                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: root.viewModel.currentStage
                    Flickable {
                        contentHeight: connectForm.implicitHeight
                        clip: true
                        ColumnLayout {
                            id: connectForm
                            width: parent.width
                            spacing: 8
                            Text { text: "사이트 연결"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                            // ponytail: 테스트용 기본값 프리필 — 배포 전 아래 text 값들 지우면 됨
                            Components.AppTextField { id: supplierName; Layout.fillWidth: true; text: "mockmall"; placeholderText: "도매처명"; Accessible.name: "도매처명"; size: "compact" }
                            Components.AppTextField { id: mainUrl; Layout.fillWidth: true; text: "http://localhost:9000/index.html"; placeholderText: "https://example.com"; Accessible.name: "메인 URL"; size: "compact" }
                            Components.AppTextField { id: soldoutUrl; Layout.fillWidth: true; placeholderText: "품절 상품 URL (권장 — 품절 감지 정확도를 높입니다)"; Accessible.name: "품절 상품 URL"; size: "compact" }
                            Components.AppTextField { id: detailUrl; Layout.fillWidth: true; text: "http://localhost:9000/detail.html?product_no=101"; placeholderText: "샘플 상품 URL (필드 매핑에 사용)"; Accessible.name: "샘플 상품 URL"; size: "compact" }
                            CheckBox { id: needsLogin; checked: true; text: "로그인 필요"; Accessible.name: text }
                            Components.AppTextField { id: loginUrl; visible: needsLogin.checked; Layout.fillWidth: true; text: "http://localhost:9000/login.html"; placeholderText: "로그인 URL"; Accessible.name: "로그인 URL"; size: "compact" }
                            Components.AppTextField { id: username; visible: needsLogin.checked; Layout.fillWidth: true; text: "test"; placeholderText: "아이디"; Accessible.name: "로그인 아이디"; size: "compact" }
                            Components.AppTextField { id: password; visible: needsLogin.checked; Layout.fillWidth: true; text: "test"; placeholderText: "비밀번호"; echoMode: TextInput.Password; Accessible.name: "로그인 비밀번호" }
                            RowLayout {
                                Components.AppButton {
                                    text: "사이트 분석"
                                    enabled: !root.viewModel.busy
                                    selected: true
                                    onClicked: {
                                        root.viewModel.setConnectionInputs({supplierName: supplierName.text, mainUrl: mainUrl.text, detailUrl: detailUrl.text, needsLogin: needsLogin.checked})
                                        root.viewModel.setSoldoutUrl(soldoutUrl.text)
                                        root.viewModel.setLoginInputs({loginUrl: loginUrl.text, username: username.text, password: password.text})
                                        root.viewModel.probe()
                                        username.text = ""
                                        password.text = ""
                                    }
                                }
                                Components.AppButton { text: "취소"; enabled: root.viewModel.busy; onClicked: root.viewModel.cancelProbe() }
                            }
                        }
                    }
                    Flickable {
                        contentHeight: analyzeForm.implicitHeight
                        clip: true
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                        ColumnLayout {
                        id: analyzeForm
                        width: parent.width
                        spacing: 8
                        Text { text: "분석 결과"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }

                        // 수집할 카테고리
                        Text {
                            Layout.fillWidth: true
                            text: "수집할 카테고리 " + (root.viewModel.probeSummary.categoryCount || 0) + "개 · " + (root.viewModel.probeSummary.encoding || "-") + " — ✕로 제외"
                            color: Ui.Theme.textMuted
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                        Components.GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 200
                            color: Ui.Theme.surfaceRaised
                            ListView {
                                id: categoryList
                                anchors.fill: parent
                                anchors.margins: 6
                                clip: true
                                model: root.viewModel.probeSummary.categories || []
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AlwaysOn }
                                delegate: RowLayout {
                                    required property var modelData
                                    width: categoryList.width - (categoryList.ScrollBar.vertical.visible ? categoryList.ScrollBar.vertical.width : 0)
                                    spacing: 4
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.name || modelData.url || ""
                                        color: Ui.Theme.text
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    ToolButton {
                                        implicitWidth: 24
                                        implicitHeight: 24
                                        text: "✕"
                                        flat: true
                                        enabled: !root.viewModel.busy
                                        onClicked: root.viewModel.setCategoryExcluded(modelData.url || modelData.name, true)
                                        ToolTip.text: "이 카테고리를 목록에서 제거"
                                        ToolTip.visible: hovered
                                        ToolTip.delay: 400
                                        Accessible.name: "카테고리 제거: " + (modelData.name || modelData.url || "")
                                    }
                                }
                            }
                        }

                        // 샘플 상품
                        Text {
                            Layout.fillWidth: true
                            text: "샘플 상품 " + ((root.viewModel.probeSummary.sampleProducts || []).length) + "개 — 프로브가 발견한 상품입니다. 3단계 필드 매핑 검증에 사용됩니다"
                            color: Ui.Theme.textMuted
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                        Components.GlassPanel {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 110
                            color: Ui.Theme.surfaceRaised
                            Text {
                                anchors.fill: parent
                                anchors.margins: 12
                                visible: (root.viewModel.probeSummary.sampleProducts || []).length === 0
                                text: "샘플 상품을 찾지 못했습니다. 아래 '수동 보정'으로 전체상품 링크를 지정하거나, 1단계에서 샘플 상품 URL을 확인하세요."
                                color: Ui.Theme.textMuted
                                font.pixelSize: 12
                                wrapMode: Text.Wrap
                                verticalAlignment: Text.AlignVCenter
                            }
                            ListView {
                                id: sampleList
                                anchors.fill: parent
                                anchors.margins: 6
                                clip: true
                                visible: (root.viewModel.probeSummary.sampleProducts || []).length > 0
                                model: root.viewModel.probeSummary.sampleProducts || []
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AlwaysOn }
                                delegate: Text {
                                    required property var modelData
                                    width: sampleList.width - (sampleList.ScrollBar.vertical.visible ? sampleList.ScrollBar.vertical.width : 0)
                                    height: 22
                                    text: (modelData.name && modelData.name !== "(이름 없음)") ? modelData.name : (modelData.url || modelData.name || "")
                                    color: Ui.Theme.text
                                    font.pixelSize: 12
                                    elide: Text.ElideMiddle
                                    verticalAlignment: Text.AlignVCenter
                                }
                            }
                        }

                        // 수동 보정 섹션 (선택사항)
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                text: "수동 보정 (선택사항)"
                                color: Ui.Theme.text
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "프로브가 자동 감지하지 못한 항목을 사이트에서 직접 클릭해 지정합니다. 브라우저가 열리면 상단 안내를 따라 요소를 클릭하세요."
                                color: Ui.Theme.textMuted
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                            // 전체상품 링크 지정
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: pickAllProductsBtn.implicitHeight
                                    radius: Ui.Theme.radiusSmall
                                    color: Qt.alpha(Ui.Theme.surfaceRaised, 0.6)
                                    border.color: Ui.Theme.border
                                    border.width: 1
                                    Components.AppButton {
                                        id: pickAllProductsBtn
                                        anchors.fill: parent
                                        text: "브라우저에서 전체상품 링크 지정"
                                        enabled: !root.viewModel.busy && !root.viewModel.allProductsAutoDetected
                                        onClicked: root.viewModel.pickAllProducts()
                                        ToolTip.text: "사이트의 '전체상품' 메뉴를 브라우저에서 직접 클릭해 지정합니다."
                                        ToolTip.visible: hovered
                                        ToolTip.delay: 400
                                        Accessible.name: text
                                        Accessible.description: ToolTip.text
                                        Accessible.role: Accessible.Button
                                    }
                                }
                                Text {
                                    visible: root.viewModel.allProductsAutoDetected
                                    text: "✓ 자동 감지됨"
                                    color: Ui.Theme.success
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                    verticalAlignment: Text.AlignVCenter
                                    Accessible.name: "전체상품 메뉴 자동 감지됨"
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "'전체상품' 페이지가 자동 감지되지 않았을 때 직접 지정"
                                color: Ui.Theme.textMuted
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                            // 카테고리 메뉴 지정
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: pickCategoryMenuBtn.implicitHeight
                                radius: Ui.Theme.radiusSmall
                                color: Qt.alpha(Ui.Theme.surfaceRaised, 0.6)
                                border.color: Ui.Theme.border
                                border.width: 1
                                Components.AppButton {
                                    id: pickCategoryMenuBtn
                                    anchors.fill: parent
                                    text: "브라우저에서 카테고리 메뉴 지정"
                                    enabled: !root.viewModel.busy
                                    onClicked: root.viewModel.pickCategoryMenu()
                                    ToolTip.text: "카테고리 메뉴 안의 대표 항목 하나를 클릭해 AI 설정 생성에 사용할 힌트로 지정합니다."
                                    ToolTip.visible: hovered
                                    ToolTip.delay: 400
                                    Accessible.name: text
                                    Accessible.description: ToolTip.text
                                    Accessible.role: Accessible.Button
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "카테고리 메뉴 항목 1개를 클릭하면 AI가 메뉴 구조를 파악하는 힌트로 사용"
                                color: Ui.Theme.textMuted
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                        }
                        // 주 액션
                        Components.InlineBanner {
                            Layout.fillWidth: true
                            visible: root.viewModel.categoryAnalysisMessage.length > 0
                            text: root.viewModel.categoryAnalysisMessage
                            severity: root.viewModel.categoryAnalysisReady ? "success" : "warning"
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Item { Layout.fillWidth: true }
                            Components.AppButton {
                                text: "AI 설정 생성"
                                selected: true
                                enabled: !root.viewModel.busy && root.viewModel.categoryAnalysisReady
                                onClicked: root.viewModel.generate()
                                Accessible.name: text
                                Accessible.description: "분석 결과를 바탕으로 어댑터 설정을 자동 생성합니다."
                                Accessible.role: Accessible.Button
                            }
                            Components.AppButton {
                                text: "취소"
                                enabled: root.viewModel.busy
                                onClicked: root.viewModel.cancelGenerate()
                                Accessible.name: text
                            }
                        }
                        }
                    }
                    ColumnLayout {
                        Text { text: "필드 매핑"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                        Components.GlassPanel {
                            Layout.fillWidth: true
                            visible: root.viewModel.needsMappingLogin
                            color: Qt.alpha(Ui.Theme.warning, 0.10)
                            border.color: Ui.Theme.warning
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 14
                                spacing: 8
                                Text { text: "로그인 필요"; color: Ui.Theme.warning; font.pixelSize: 13; font.weight: Font.DemiBold }
                                Text {
                                    Layout.fillWidth: true
                                    text: "이 사이트는 로그인이 필요합니다. 로그인 정보를 입력하면 브라우저가 자동으로 로그인한 뒤 요소를 선택합니다."
                                    color: Ui.Theme.textMuted
                                    font.pixelSize: 11
                                    wrapMode: Text.Wrap
                                }
                                Components.AppTextField { id: mappingLoginUrl; Layout.fillWidth: true; placeholderText: "로그인 URL"; Accessible.name: "매핑 로그인 URL"; size: "compact" }
                                Components.AppTextField { id: mappingUsername; Layout.fillWidth: true; placeholderText: "아이디"; Accessible.name: "매핑 로그인 아이디"; size: "compact" }
                                Components.AppTextField { id: mappingPassword; Layout.fillWidth: true; placeholderText: "비밀번호"; echoMode: TextInput.Password; Accessible.name: "매핑 로그인 비밀번호" }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Item { Layout.fillWidth: true }
                                    Components.AppButton {
                                        text: "로그인 후 선택"
                                        selected: true
                                        enabled: mappingLoginUrl.text.length > 0 && mappingUsername.text.length > 0 && mappingPassword.text.length > 0 && !root.viewModel.busy
                                        onClicked: {
                                            root.viewModel.submitMappingLogin({loginUrl: mappingLoginUrl.text, username: mappingUsername.text, password: mappingPassword.text})
                                            mappingUsername.text = ""
                                            mappingPassword.text = ""
                                        }
                                        Accessible.name: text
                                        Accessible.description: "입력한 로그인 정보로 브라우저에 자동 로그인한 뒤 요소 선택을 다시 시작합니다."
                                        Accessible.role: Accessible.Button
                                    }
                                }
                            }
                        }

                        Components.MappingTable { Layout.fillWidth: true; Layout.fillHeight: true; model: root.viewModel.mappingRows; viewModel: root.viewModel }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text {
                                text: "대상 URL"
                                color: Ui.Theme.textMuted
                                font.pixelSize: 11
                            }
                            Components.AppTextField {
                                id: manualTestUrl
                                Layout.fillWidth: true
                                text: root.viewModel.connectionInputs.detailUrl || ""
                                placeholderText: "요소 선택 시 이동할 상품 상세 URL"
                                Accessible.name: "매핑 대상 상품 URL"
                                ToolTip.text: "요소 선택 시 이 상품 페이지로 이동합니다. 다른 상품으로 바꾸려면 URL을 수정하세요."
                                size: "compact"
                                onEditingFinished: root.viewModel.setDetailUrl(text)
                            }
                        }
                        Components.InlineBanner {
                            Layout.fillWidth: true
                            visible: root.viewModel.previewActive
                            text: "브라우저에서 매핑된 필드가 파란색 박스로 표시됩니다. 확인 후 닫기를 누르세요."
                            severity: "info"
                        }
                        RowLayout {
                            spacing: 8
                            Components.AppButton {
                                text: root.viewModel.previewActive ? "미리보기 닫기" : "매핑 미리보기"
                                // 미리보기가 열린 동안에는 busy여도 닫을 수 있어야 함.
                                enabled: root.viewModel.previewActive || !root.viewModel.busy
                                onClicked: root.viewModel.previewActive ? root.viewModel.closePreview() : root.viewModel.previewMapping()
                                ToolTip.text: "브라우저에서 매핑된 필드를 파란 박스로 표시만 합니다 (값은 채우지 않음)."
                                Accessible.name: text
                            }
                            Components.AppButton {
                                text: "값 가져오기"
                                selected: true
                                enabled: !root.viewModel.busy
                                onClicked: root.viewModel.fetchFieldValues()
                                ToolTip.text: "브라우저 없이 각 필드의 실제 값을 추출해 아래 목록에 채웁니다."
                                Accessible.name: text
                            }
                            Item { Layout.fillWidth: true }
                            Components.AppButton {
                                text: "전체 테스트"
                                selected: true
                                enabled: !root.viewModel.busy
                                onClicked: root.viewModel.testAll()
                                Accessible.name: text
                            }
                        }
                    }
                    ColumnLayout {
                        spacing: 8
                        Text { text: "검증 및 저장"; color: Ui.Theme.text; font.pixelSize: 20; font.weight: Font.Bold }
                        Text { text: root.viewModel.validationSummary.message || "검증이 필요합니다."; color: root.viewModel.canSave ? Ui.Theme.success : Ui.Theme.warning }
                        Text { text: "테스트 상품 " + (root.viewModel.testUrls.length || 0) + "개"; color: Ui.Theme.textMuted }
                        Components.InlineBanner {
                            Layout.fillWidth: true
                            visible: Boolean(root.viewModel.saveWarning.message)
                            text: root.viewModel.saveWarning.message || ""
                            severity: "warning"
                        }
                        // 테스트 상품이 3개 미만이면 URL 추가 요청
                        Components.GlassPanel {
                            Layout.fillWidth: true
                            visible: root.viewModel.needsMoreTestUrls
                            implicitHeight: addUrlCol.implicitHeight + 24
                            color: Qt.alpha(Ui.Theme.warning, 0.10)
                            border.color: Ui.Theme.warning
                            ColumnLayout {
                                id: addUrlCol
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 6
                                Text {
                                    Layout.fillWidth: true
                                    text: "자동으로 찾은 테스트 상품이 " + (root.viewModel.testUrls.length || 0) + "개뿐입니다. 정확한 검증을 위해 상품 상세 URL을 3개까지 추가해 주세요."
                                    color: Ui.Theme.warning
                                    font.pixelSize: 12
                                    wrapMode: Text.Wrap
                                }
                                Repeater {
                                    model: root.viewModel.testUrls
                                    delegate: RowLayout {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Text { Layout.fillWidth: true; text: modelData; color: Ui.Theme.textMuted; font.pixelSize: 11; elide: Text.ElideMiddle }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Components.AppTextField {
                                        id: extraUrlField
                                        Layout.fillWidth: true
                                        placeholderText: "추가할 상품 상세 URL (https://...)"
                                        size: "compact"
                                        Accessible.name: "추가 테스트 상품 URL"
                                        onAccepted: if (root.viewModel.addTestUrl(text)) text = ""
                                    }
                                    Components.AppButton {
                                        text: "추가"
                                        enabled: !root.viewModel.busy && extraUrlField.text.length > 0
                                        onClicked: if (root.viewModel.addTestUrl(extraUrlField.text)) extraUrlField.text = ""
                                    }
                                }
                            }
                        }
                        Components.ValidationProducts {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            model: root.viewModel.validationProducts
                        }
                        RowLayout {
                            Components.AppButton { text: "매핑 수정"; enabled: !root.viewModel.busy; onClicked: root.viewModel.setCurrentStage(2) }
                            Components.AppButton { text: "검증 실행"; enabled: !root.viewModel.busy; onClicked: root.viewModel.testAll() }
                            Components.AppButton {
                                visible: Boolean(root.viewModel.saveWarning.allowContinue)
                                text: "확인하고 저장"
                                enabled: !root.viewModel.busy
                                onClicked: {
                                    root.viewModel.acknowledgeSaveWarning()
                                    if (root.viewModel.save() && root.toastHost) root.toastHost.showMessage("쇼핑몰이 등록되었습니다", "info")
                                }
                            }
                            Components.AppButton { text: "저장하고 도매처 등록"; selected: true; enabled: !root.viewModel.busy; onClicked: { if (root.viewModel.save() && root.toastHost) root.toastHost.showMessage("쇼핑몰이 등록되었습니다", "info") } }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Item { Layout.fillWidth: true }
                    Text {
                        text: (root.viewModel.advancedEditorOpen ? "▾ " : "▸ ") + "고급 YAML 편집"
                        color: yamlToggleHover.containsMouse ? Ui.Theme.text : Ui.Theme.textMuted
                        font.pixelSize: 11
                        MouseArea {
                            id: yamlToggleHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.viewModel.setAdvancedEditorOpen(!root.viewModel.advancedEditorOpen)
                        }
                    }
                }
                Components.YamlEditor {
                    visible: root.viewModel.advancedEditorOpen
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? Math.min(260, root.height * 0.35) : 0
                    viewModel: root.viewModel
                }
            }
        }
    }

    Dialog {
        id: pickedHintDialog
        objectName: "pickedHintConfirmDialog"
        parent: Overlay.overlay
        x: Math.round((parent.width - width) / 2)
        y: Math.round((parent.height - height) / 2)
        modal: true
        visible: root.viewModel.hasPendingHint
        width: Math.min(root.width - 40, 460)
        closePolicy: Popup.NoAutoClose

        contentItem: ColumnLayout {
            spacing: 10
            Text {
                Layout.fillWidth: true
                text: "「" + root.viewModel.pickerFieldLabel + "」에 이 요소를 사용할까요?"
                color: Ui.Theme.text
                wrapMode: Text.Wrap
                font.pixelSize: 15
                font.weight: Font.DemiBold
            }
            Text {
                Layout.fillWidth: true
                text: root.viewModel.pendingHintPreview
                color: Ui.Theme.text
                wrapMode: Text.WrapAnywhere
                font.family: "monospace"
                font.pixelSize: 12
            }
            Text {
                Layout.fillWidth: true
                text: "Yes를 누르면 브라우저를 닫고 이 선택을 매핑에 사용합니다."
                color: Ui.Theme.textMuted
                wrapMode: Text.Wrap
                font.pixelSize: 11
            }
        }
        footer: RowLayout {
            spacing: 8
            Item { Layout.fillWidth: true }
            Components.AppButton {
                text: "No"
                enabled: !root.viewModel.busy
                onClicked: root.viewModel.reselectPickedHint()
            }
            Components.AppButton {
                text: "Yes"
                selected: true
                enabled: root.viewModel.canAcceptPickedHint
                onClicked: root.viewModel.acceptPickedHint()
            }
        }
        background: Rectangle {
            color: Ui.Theme.surface
            border.color: Ui.Theme.border
            border.width: 1
            radius: Ui.Theme.radiusLarge
        }
    }
}
