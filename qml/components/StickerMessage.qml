import "../ut_components"
import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7

Item {
    id: root

    property string copyableText: ""
    property bool isOutgoing: false
    property bool isGroup: false
    property string timestamp: ""
    property string stickerSource: ""
    property string thumbnailSource: ""
    property string mediaPath: ""
    property string senderName: ""
    property string senderPhoto: ""
    property string replyToId: ""
    property string replyToSender: ""
    property string replyToText: ""
    property bool showSender: isGroup && !isOutgoing && senderName !== ""

    signal replyClicked(string messageId)

    width: parent.width
    height: stickerContainer.height + units.gu(0.5)

    Rectangle {
        id: stickerAvatar

        width: units.gu(3.5)
        height: units.gu(3.5)
        radius: width / 2
        color: theme.palette.normal.base
        visible: root.showSender

        anchors {
            left: parent.left
            bottom: stickerContainer.bottom
            leftMargin: units.gu(1)
        }

        Image {
            id: stickerAvatarImg

            anchors.fill: parent
            source: root.senderPhoto || ""
            fillMode: Image.PreserveAspectCrop
            visible: false
        }

        Rectangle {
            id: stickerAvatarMask

            anchors.fill: parent
            radius: width / 2
            visible: false
        }

        OpacityMask {
            anchors.fill: parent
            source: stickerAvatarImg
            maskSource: stickerAvatarMask
            visible: !!root.senderPhoto
        }

        Icon {
            anchors.centerIn: parent
            name: "contact"
            width: units.gu(2)
            height: units.gu(2)
            color: theme.palette.normal.backgroundSecondaryText
            visible: !root.senderPhoto
        }

    }

    Column {
        id: stickerContainer

        spacing: units.gu(0.3)

        anchors {
            right: isOutgoing ? parent.right : undefined
            left: isOutgoing ? undefined : parent.left
            rightMargin: isOutgoing ? units.gu(2) : units.gu(8)
            leftMargin: isOutgoing ? units.gu(8) : (root.showSender ? units.gu(5.5) : units.gu(2))
        }

        Rectangle {
            visible: root.replyToId !== ""
            width: units.gu(16)
            height: replyColumn.height + units.gu(0.8)
            radius: units.gu(0.5)
            color: Qt.rgba(0, 0, 0, 0.06)

            MouseArea {
                anchors.fill: parent
                onClicked: root.replyClicked(root.replyToId)
            }

            Rectangle {
                id: replyBar

                width: units.gu(0.3)
                height: parent.height
                radius: units.gu(0.15)
                color: LomiriColors.blue
            }

            Column {
                id: replyColumn

                spacing: units.gu(0.1)

                anchors {
                    left: replyBar.right
                    right: parent.right
                    top: parent.top
                    leftMargin: units.gu(0.6)
                    rightMargin: units.gu(0.5)
                    topMargin: units.gu(0.4)
                }

                Label {
                    text: root.replyToSender
                    fontSize: "small"
                    font.bold: true
                    color: LomiriColors.blue
                    elide: Text.ElideRight
                    width: parent.width
                    visible: text !== ""
                }

                Label {
                    text: root.replyToText
                    fontSize: "small"
                    color: "#666666"
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    wrapMode: Text.NoWrap
                    width: parent.width
                    visible: text !== ""
                }

            }

        }

        Label {
            text: root.senderName
            fontSize: "x-small"
            font.bold: true
            color: LomiriColors.blue
            visible: root.showSender
            elide: Text.ElideRight
            width: units.gu(16)
        }

        Rectangle {
            width: units.gu(16)
            height: units.gu(16)
            color: "transparent"

            Image {
                anchors.fill: parent
                source: root.mediaPath || root.thumbnailSource || root.stickerSource
                fillMode: Image.PreserveAspectFit
                visible: source != ""
            }

            Icon {
                anchors.centerIn: parent
                name: "emoji-recent-symbolic"
                width: units.gu(8)
                height: units.gu(8)
                color: theme.palette.normal.backgroundSecondaryText
                visible: !root.mediaPath && !root.thumbnailSource && !root.stickerSource
            }

        }

        Label {
            text: root.timestamp
            fontSize: "xx-small"
            color: "#999999"
        }

    }

}
