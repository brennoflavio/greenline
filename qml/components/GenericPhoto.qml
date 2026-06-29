import Lomiri.Components 1.3
import Lomiri.Components 1.3 as UITK
import QtQuick 2.7

Item {
    id: root

    property string photoPath: ""
    property string fallbackIconName: "contact"
    property color avatarColor: theme.palette.normal.base
    property color fallbackIconColor: theme.palette.normal.backgroundSecondaryText
    property real fallbackIconWidth: units.gu(3)
    property real fallbackIconHeight: fallbackIconWidth
    readonly property bool photoExists: photoPath !== ""

    function refreshShape() {
        effectSource.scheduleUpdate();
    }

    onPhotoPathChanged: refreshShape()
    onAvatarColorChanged: refreshShape()
    onWidthChanged: refreshShape()
    onHeightChanged: refreshShape()
    Component.onCompleted: refreshShape()

    ShaderEffectSource {
        id: effectSource

        anchors.centerIn: parent
        width: 0
        height: 0
        live: false
        sourceItem: imageContent
    }

    Item {
        id: imageContent

        anchors.fill: parent
        visible: false

        Rectangle {
            anchors.fill: parent
            color: root.avatarColor
        }

        Image {
            id: itemPicture

            anchors.centerIn: parent
            width: parent.width
            height: parent.height
            source: root.photoPath
            sourceSize: Qt.size(Math.ceil(width * 2), Math.ceil(height * 2))
            fillMode: Image.PreserveAspectCrop
            antialiasing: true
            asynchronous: true
            cache: true
            mipmap: true
            onStatusChanged: {
                if (status === Image.Ready || status === Image.Error)
                    root.refreshShape();

            }
        }

    }

    UITK.Shape {
        id: imgShape

        image: effectSource
        anchors.fill: parent
        aspect: UITK.LomiriShape.DropShadow
        radius: width > units.gu(7) ? "medium" : "small"
    }

    Icon {
        anchors.centerIn: parent
        name: root.fallbackIconName
        width: root.fallbackIconWidth
        height: root.fallbackIconHeight
        color: root.fallbackIconColor
        visible: !root.photoExists
    }

}
