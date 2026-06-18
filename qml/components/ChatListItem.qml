import "../lib/ChatHelpers.js" as ChatHelpers
import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7
import QtQuick.Layouts 1.3

ListItem {
    id: root

    property var chat: ({
    })
    property bool swipeActionsEnabled: true

    signal muteRequested(string chatId)
    signal archiveRequested(string chatId)

    height: units.gu(8)
    leadingActions: root.swipeActionsEnabled ? chatActions : null

    RowLayout {
        spacing: units.gu(1.5)

        anchors {
            fill: parent
            leftMargin: units.gu(2)
            rightMargin: units.gu(2)
            topMargin: units.gu(1)
            bottomMargin: units.gu(1)
        }

        Rectangle {
            width: units.gu(6)
            height: units.gu(6)
            radius: width / 2
            color: theme.palette.normal.base
            Layout.alignment: Qt.AlignVCenter

            Image {
                id: avatarImage

                anchors.fill: parent
                source: root.chat.photo || ""
                fillMode: Image.PreserveAspectCrop
                visible: false
            }

            Rectangle {
                id: avatarMask

                anchors.fill: parent
                radius: width / 2
                visible: false
            }

            OpacityMask {
                anchors.fill: parent
                source: avatarImage
                maskSource: avatarMask
                visible: !!root.chat.photo
            }

            Icon {
                anchors.centerIn: parent
                name: "contact"
                width: units.gu(3)
                height: units.gu(3)
                color: theme.palette.normal.backgroundSecondaryText
                visible: !root.chat.photo
            }

        }

        Column {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: units.gu(0.3)

            RowLayout {
                width: parent.width

                Label {
                    text: root.chat.name || ""
                    fontSize: "medium"
                    font.bold: root.chat.unread_count > 0
                    color: theme.palette.normal.foregroundText
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                Icon {
                    name: "audio-volume-muted"
                    height: units.gu(2)
                    width: units.gu(2)
                    color: theme.palette.normal.backgroundTertiaryText
                    visible: !!root.chat.muted
                    Layout.alignment: Qt.AlignRight
                }

                Label {
                    text: root.chat.date || ""
                    fontSize: "x-small"
                    color: root.chat.unread_count > 0 ? LomiriColors.green : theme.palette.normal.backgroundTertiaryText
                    Layout.alignment: Qt.AlignRight
                }

            }

            RowLayout {
                width: parent.width

                Row {
                    spacing: units.gu(0.3)
                    Layout.fillWidth: true

                    MessageReceiptIcon {
                        id: receiptIcon

                        height: units.gu(1.6)
                        width: units.gu(1.6)
                        readReceipt: root.chat.read_receipt
                        inactiveColor: theme.palette.normal.backgroundTertiaryText
                        activeColor: LomiriColors.lightBlue
                        indicatorVisible: !root.chat.has_draft
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Label {
                        text: ChatHelpers.chatPreview(root.chat, i18n)
                        fontSize: "small"
                        color: theme.palette.normal.backgroundTertiaryText
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        width: parent.parent.width - (receiptIcon.visible ? units.gu(2) : 0) - parent.spacing - (unreadBadge.visible ? unreadBadge.width + units.gu(0.5) : 0)
                        anchors.verticalCenter: parent.verticalCenter
                    }

                }

                Rectangle {
                    id: unreadBadge

                    width: units.gu(2.5)
                    height: units.gu(2.5)
                    radius: width / 2
                    color: LomiriColors.green
                    visible: root.chat.unread_count > 0
                    Layout.alignment: Qt.AlignRight

                    Label {
                        anchors.centerIn: parent
                        text: root.chat.unread_count
                        fontSize: "x-small"
                        color: "white"
                        font.bold: true
                    }

                }

            }

        }

    }

    ListItemActions {
        id: chatActions

        actions: [
            Action {
                iconName: root.chat.muted ? "audio-volume-high" : "audio-volume-muted"
                text: root.chat.muted ? i18n.tr("Unmute") : i18n.tr("Mute")
                onTriggered: root.muteRequested(root.chat.id)
            },
            Action {
                iconName: "document-save"
                text: root.chat.archived ? i18n.tr("Unarchive") : i18n.tr("Archive")
                onTriggered: root.archiveRequested(root.chat.id)
            }
        ]
    }

}
