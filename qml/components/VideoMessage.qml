import "../ut_components"
import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string thumbnailSource: ""
    property string mediaPath: ""
    property string caption: ""
    property string duration: ""
    property bool downloading: false

    signal downloadRequested()

    copyableText: caption

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

        Rectangle {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: units.gu(0.5)
            width: durationLabel.width + units.gu(1)
            height: durationLabel.height + units.gu(0.4)
            radius: units.gu(0.3)
            color: "#80000000"
            visible: root.duration !== ""

            Label {
                id: durationLabel

                anchors.centerIn: parent
                text: root.duration
                fontSize: "x-small"
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
                if (root.mediaPath)
                    pageStack.push(Qt.resolvedUrl("../VideoPreviewPage.qml"), {
                    "videoPath": root.mediaPath
                });
                else if (!root.downloading)
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
