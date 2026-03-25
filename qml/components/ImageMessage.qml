import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string imageSource: ""
    property string caption: ""

    Rectangle {
        width: parent.width
        height: units.gu(20)
        radius: units.gu(0.5)
        color: theme.palette.normal.base
        clip: true

        Image {
            anchors.fill: parent
            source: root.imageSource
            fillMode: Image.PreserveAspectCrop
            visible: source != ""
        }

        Icon {
            anchors.centerIn: parent
            name: "image-x-generic-symbolic"
            width: units.gu(4)
            height: units.gu(4)
            color: theme.palette.normal.backgroundSecondaryText
            visible: root.imageSource === ""
        }

    }

    Label {
        text: root.caption
        fontSize: "small"
        color: "#303030"
        wrapMode: Text.WordWrap
        width: parent.width
        visible: text !== ""
    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
