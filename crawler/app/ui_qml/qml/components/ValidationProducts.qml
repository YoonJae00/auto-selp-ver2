pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".." as Ui

// 검증 단계: 샘플 상품들을 매핑 필드별로 나란히 카드로 표시.
Item {
    id: root
    property var model: []

    Text {
        anchors.fill: parent
        visible: !root.model || root.model.length === 0
        text: "검증을 실행하면 샘플 상품의 추출 결과가 여기에 표시됩니다."
        color: Ui.Theme.textMuted
        wrapMode: Text.WordWrap
        font.pixelSize: 12
    }

    ScrollView {
        anchors.fill: parent
        visible: root.model && root.model.length > 0
        clip: true
        contentWidth: availableWidth

        RowLayout {
            width: root.width
            spacing: 8
            Repeater {
                model: root.model
                delegate: Rectangle {
                    id: card
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignTop
                    Layout.preferredWidth: 1
                    implicitHeight: cardCol.implicitHeight + 20
                    radius: 8
                    color: Ui.Theme.surfaceRaised
                    border.color: Ui.Theme.border

                    ColumnLayout {
                        id: cardCol
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 6

                        Text {
                            text: "상품 " + card.modelData.index
                            color: Ui.Theme.textMuted
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                        }
                        Image {
                            visible: card.modelData.imageUrl !== ""
                            source: card.modelData.imageUrl || ""
                            Layout.preferredWidth: 80
                            Layout.preferredHeight: 80
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }
                        Text {
                            Layout.fillWidth: true
                            text: card.modelData.name || "(이름 없음)"
                            color: Ui.Theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Ui.Theme.border }
                        Repeater {
                            model: card.modelData.fields
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 4
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Text {
                                        text: modelData.label
                                        color: Ui.Theme.textMuted
                                        font.pixelSize: 11
                                        Layout.preferredWidth: 64
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: modelData.value || "—"
                                        color: modelData.value === "" ? Ui.Theme.textMuted : (modelData.ok ? Ui.Theme.success : Ui.Theme.danger)
                                        font.pixelSize: 11
                                        wrapMode: Text.WrapAnywhere
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                    }
                                }
                                RowLayout {
                                    visible: modelData.imageUrls && modelData.imageUrls.length > 0
                                    Layout.leftMargin: 70
                                    spacing: 4
                                    Repeater {
                                        model: modelData.imageUrls || []
                                        delegate: Image {
                                            required property string modelData
                                            source: modelData
                                            Layout.preferredWidth: 34
                                            Layout.preferredHeight: 34
                                            fillMode: Image.PreserveAspectFit
                                            asynchronous: true
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
