import Lomiri.Components 1.3
import QtQuick 2.7

Rectangle {
    id: root

    property string sender: ""
    property string previewText: ""

    signal clearRequested()

    height: visible ? replyPreviewColumn.height + units.gu(1) : 0
    radius: units.gu(0.6)
    color: theme.palette.normal.base

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
            text: root.sender
            fontSize: "small"
            font.bold: true
            color: LomiriColors.blue
            elide: Text.ElideRight
            width: parent.width
        }

        Label {
            text: root.previewText
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
            onClicked: root.clearRequested()
        }

    }

}
