import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3

MessageBubble {
    id: root

    property var images: []
    property string caption: ""

    copyableText: caption

    GridLayout {
        width: parent.width
        columns: Math.min(root.images.length, 2)
        rowSpacing: units.gu(0.3)
        columnSpacing: units.gu(0.3)

        Repeater {
            model: root.images

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: units.gu(12)
                radius: units.gu(0.5)
                color: theme.palette.normal.base
                clip: true

                Image {
                    anchors.fill: parent
                    source: modelData || ""
                    fillMode: Image.PreserveAspectCrop
                    visible: source != ""
                }

                Icon {
                    anchors.centerIn: parent
                    name: "image-x-generic-symbolic"
                    width: units.gu(3)
                    height: units.gu(3)
                    color: theme.palette.normal.backgroundSecondaryText
                    visible: (modelData || "") === ""
                }

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
