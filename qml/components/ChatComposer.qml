import Lomiri.Components 1.3
import QtQuick 2.7

Rectangle {
    id: root

    property string replyToMessageId: ""
    property string replyToSender: ""
    property string replyToText: ""
    property alias text: messageInput.text

    signal clearReplyRequested()
    signal attachmentRequested()
    signal sendRequested()

    function focusInput() {
        messageInput.forceActiveFocus();
    }

    height: inputRow.height + units.gu(2) + (replyPreview.visible ? replyPreview.height + inputColumn.spacing : 0)
    color: theme.palette.normal.background

    Rectangle {
        height: units.dp(1)
        color: theme.palette.normal.base

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }

    }

    Column {
        id: inputColumn

        spacing: units.gu(0.5)

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            topMargin: units.gu(1)
            leftMargin: units.gu(1)
            rightMargin: units.gu(1)
        }

        Rectangle {
            id: replyPreview

            width: parent.width
            height: replyPreviewColumn.height + units.gu(1)
            radius: units.gu(0.6)
            color: theme.palette.normal.base
            visible: root.replyToMessageId !== ""

            Rectangle {
                width: units.gu(0.3)
                height: parent.height
                radius: units.gu(0.15)
                color: LomiriColors.blue
            }

            Column {
                id: replyPreviewColumn

                spacing: units.gu(0.1)

                anchors {
                    left: parent.left
                    right: clearReplyIcon.left
                    top: parent.top
                    leftMargin: units.gu(0.8)
                    rightMargin: units.gu(0.6)
                    topMargin: units.gu(0.5)
                }

                Label {
                    text: root.replyToSender
                    fontSize: "small"
                    font.bold: true
                    color: LomiriColors.blue
                    elide: Text.ElideRight
                    width: parent.width
                }

                Label {
                    text: root.replyToText
                    fontSize: "small"
                    color: theme.palette.normal.backgroundSecondaryText
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    wrapMode: Text.NoWrap
                    width: parent.width
                }

            }

            Icon {
                id: clearReplyIcon

                name: "close"
                width: units.gu(2.2)
                height: units.gu(2.2)
                color: theme.palette.normal.backgroundSecondaryText

                anchors {
                    right: parent.right
                    rightMargin: units.gu(0.8)
                    verticalCenter: parent.verticalCenter
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.clearReplyRequested()
                }

            }

        }

        Item {
            id: inputRow

            width: parent.width
            height: Math.max(messageInput.height, attachmentIcon.height, sendIcon.height)

            Icon {
                id: attachmentIcon

                name: "attachment"
                width: units.gu(3)
                height: units.gu(3)
                color: theme.palette.normal.backgroundSecondaryText

                anchors {
                    left: parent.left
                    verticalCenter: messageInput.verticalCenter
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.attachmentRequested()
                }

            }

            Icon {
                id: sendIcon

                name: "send"
                width: units.gu(3)
                height: units.gu(3)
                color: LomiriColors.green

                anchors {
                    right: parent.right
                    verticalCenter: messageInput.verticalCenter
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.sendRequested()
                }

            }

            TextArea {
                id: messageInput

                placeholderText: i18n.tr("Type a message...")
                autoSize: true
                maximumLineCount: 5

                anchors {
                    left: attachmentIcon.right
                    right: sendIcon.left
                    verticalCenter: parent.verticalCenter
                    leftMargin: units.gu(1)
                    rightMargin: units.gu(1)
                }

            }

        }

    }

}
