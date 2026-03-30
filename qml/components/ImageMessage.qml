import "../ut_components"
import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string imageSource: ""
    property string thumbnailSource: ""
    property string mediaPath: ""
    property string caption: ""
    property bool downloading: false

    signal downloadRequested()

    Rectangle {
        id: imageContainer

        property real aspectRatio: img.status === Image.Ready && img.implicitWidth > 0 ? img.implicitWidth / img.implicitHeight : 4 / 3

        implicitWidth: aspectRatio >= 1 ? units.gu(28) : Math.min(units.gu(30) * aspectRatio, units.gu(28))
        width: parent.width
        height: Math.min(width / aspectRatio, units.gu(35))
        radius: units.gu(0.5)
        color: theme.palette.normal.base
        clip: true

        Image {
            id: img

            anchors.fill: parent
            source: root.mediaPath || root.thumbnailSource || root.imageSource
            fillMode: Image.PreserveAspectCrop
            visible: source != ""
        }

        Icon {
            anchors.centerIn: parent
            name: "image-x-generic-symbolic"
            width: units.gu(4)
            height: units.gu(4)
            color: theme.palette.normal.backgroundSecondaryText
            visible: !root.mediaPath && !root.thumbnailSource && !root.imageSource
        }

        Rectangle {
            anchors.centerIn: parent
            width: units.gu(5)
            height: units.gu(5)
            radius: width / 2
            color: "#80000000"
            visible: !root.mediaPath && !root.downloading && (root.thumbnailSource || root.imageSource)

            Icon {
                anchors.centerIn: parent
                name: "save"
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
                if (root.mediaPath)
                    pageStack.push(Qt.resolvedUrl("../ImagePreviewPage.qml"), {
                    "imagePath": root.mediaPath
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
