import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string stickerSource: ""
    property string thumbnailSource: ""
    property string mediaPath: ""

    bubbleColor: "transparent"
    preferredBubbleWidth: units.gu(17)

    Rectangle {
        width: parent.width
        height: units.gu(16)
        color: "transparent"

        Image {
            anchors.fill: parent
            source: root.mediaPath || root.thumbnailSource || root.stickerSource
            fillMode: Image.PreserveAspectFit
            visible: source !== ""
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

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
