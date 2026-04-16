import "../ut_components"
import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3

MessageBubble {
    id: root

    property string text: ""
    property string linkTitle: ""
    property string linkDescription: ""
    property string linkUrl: ""
    property string thumbnailSource: ""

    copyableText: text || linkUrl

    Rectangle {
        width: parent.width
        height: previewColumn.height
        radius: units.gu(0.5)
        color: Qt.rgba(0, 0, 0, 0.06)
        clip: true

        MouseArea {
            anchors.fill: previewColumn
            onClicked: {
                if (root.linkUrl)
                    Qt.openUrlExternally(root.linkUrl);

            }
        }

        Column {
            id: previewColumn

            width: parent.width
            spacing: 0

            Image {
                width: parent.width
                height: status === Image.Ready && implicitWidth > 0 && implicitHeight > 0 ? Math.min(width / (implicitWidth / implicitHeight), units.gu(20)) : 0
                source: root.thumbnailSource
                fillMode: Image.PreserveAspectCrop
                visible: status === Image.Ready
            }

            Column {
                width: parent.width
                spacing: units.gu(0.3)
                topPadding: units.gu(0.8)
                bottomPadding: units.gu(0.8)
                leftPadding: units.gu(0.8)
                rightPadding: units.gu(0.8)

                Label {
                    text: root.linkTitle
                    fontSize: "small"
                    font.bold: true
                    color: "#303030"
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    width: parent.width - units.gu(1.6)
                    visible: text !== ""
                }

                Label {
                    text: root.linkDescription
                    fontSize: "x-small"
                    color: "#666666"
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    width: parent.width - units.gu(1.6)
                    visible: text !== ""
                }

                Label {
                    text: {
                        if (!root.linkUrl)
                            return "";

                        try {
                            var url = new URL(root.linkUrl);
                            return url.hostname;
                        } catch (e) {
                            return root.linkUrl;
                        }
                    }
                    fontSize: "x-small"
                    color: "#999999"
                    elide: Text.ElideRight
                    width: parent.width - units.gu(1.6)
                    visible: text !== ""
                }

            }

        }

    }

    Label {
        text: root.text
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
