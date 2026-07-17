import "../ut_components"
import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3

MessageBubble {
    id: root

    property string text: ""
    property string formattedText: ""
    property string linkTitle: ""
    property string linkDescription: ""
    property string linkUrl: ""
    property string thumbnailSource: ""
    readonly property bool usesFormattedText: formattedText !== ""
    readonly property string displayText: usesFormattedText ? formattedText : text

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
                height: source !== "" ? units.gu(12) : 0
                source: root.thumbnailSource
                fillMode: Image.PreserveAspectCrop
                visible: source !== ""
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
                    wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    width: parent.width - units.gu(1.6)
                    visible: text !== ""
                }

                Label {
                    text: root.linkDescription
                    fontSize: "x-small"
                    color: "#666666"
                    wrapMode: Text.WrapAtWordBoundaryOrAnywhere
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
        text: root.displayText
        textFormat: root.usesFormattedText ? Text.RichText : Text.PlainText
        onLinkActivated: Qt.openUrlExternally(link)
        fontSize: "small"
        color: "#303030"
        wrapMode: Text.WrapAtWordBoundaryOrAnywhere
        width: parent.width
        visible: text !== ""
    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
