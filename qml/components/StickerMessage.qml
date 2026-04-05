import "../ut_components"
import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7

Item {
    id: root

    property bool isOutgoing: false
    property bool isGroup: false
    property string timestamp: ""
    property string stickerSource: ""
    property string thumbnailSource: ""
    property string mediaPath: ""
    property string senderName: ""
    property string senderPhoto: ""
    property bool showSender: isGroup && !isOutgoing && senderName !== ""

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

        Label {
            text: root.senderName
            fontSize: "x-small"
            font.bold: true
            color: LomiriColors.blue
            visible: root.showSender
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
