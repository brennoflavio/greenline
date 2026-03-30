import "../ut_components"
import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string thumbnailSource: ""
    property string mediaPath: ""
    property string caption: ""
    property bool downloading: false

    signal downloadRequested()

    Rectangle {
        width: parent.width
        height: units.gu(20)
        radius: units.gu(0.5)
        color: theme.palette.normal.base
        clip: true

        Image {
            anchors.fill: parent
            source: root.thumbnailSource
            fillMode: Image.PreserveAspectCrop
            visible: source != "" && !root.mediaPath
        }

        Icon {
            anchors.centerIn: parent
            name: "camcorder"
            width: units.gu(4)
            height: units.gu(4)
            color: theme.palette.normal.backgroundSecondaryText
            visible: !root.thumbnailSource && !root.mediaPath
        }

        Rectangle {
            anchors.centerIn: parent
            width: units.gu(5)
            height: units.gu(5)
            radius: width / 2
            color: "#80000000"
            visible: !root.downloading

            Icon {
                anchors.centerIn: parent
                name: root.mediaPath ? "media-playback-start" : "save"
                width: units.gu(3)
                height: units.gu(3)
                color: "white"
            }

        }

        LoadingSpinner {
            anchors.centerIn: parent
            running: root.downloading
            visible: root.downloading
        }

        MouseArea {
            anchors.fill: parent
            onClicked: {
                if (!root.mediaPath && !root.downloading)
                    root.downloadRequested();

            }
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
