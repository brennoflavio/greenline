import Lomiri.Components 1.3
import QtQuick 2.7

Item {
    id: root

    property bool isOutgoing: false
    property string timestamp: ""
    property string stickerSource: ""

    width: parent.width
    height: stickerContainer.height + units.gu(0.5)

    Column {
        id: stickerContainer

        spacing: units.gu(0.3)

        anchors {
            right: isOutgoing ? parent.right : undefined
            left: isOutgoing ? undefined : parent.left
            rightMargin: isOutgoing ? units.gu(2) : units.gu(8)
            leftMargin: isOutgoing ? units.gu(8) : units.gu(2)
        }

        Rectangle {
            width: units.gu(16)
            height: units.gu(16)
            color: "transparent"

            Image {
                anchors.fill: parent
                source: root.stickerSource
                fillMode: Image.PreserveAspectFit
                visible: source != ""
            }

            Icon {
                anchors.centerIn: parent
                name: "emoji-recent-symbolic"
                width: units.gu(8)
                height: units.gu(8)
                color: theme.palette.normal.backgroundSecondaryText
                visible: root.stickerSource === ""
            }

        }

        Label {
            text: root.timestamp
            fontSize: "xx-small"
            color: "#999999"
        }

    }

}
