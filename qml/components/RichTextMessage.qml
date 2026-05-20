import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string text: ""
    property string buttonText: ""
    property string buttonUrl: ""
    property bool expanded: false
    property int collapsedLineCount: 10
    readonly property bool hasOpenableButton: buttonText !== "" && (buttonUrl.indexOf("https://") === 0 || buttonUrl.indexOf("http://") === 0)
    readonly property real senderWidthHint: showSender ? senderMeasure.implicitWidth + units.gu(2) : 0
    readonly property real replyWidthHint: replyToId !== "" ? Math.max(replySenderMeasure.implicitWidth, replyTextMeasure.implicitWidth) + units.gu(3.5) : 0
    readonly property real buttonWidthHint: hasOpenableButton ? units.gu(24) : 0
    readonly property bool shouldCollapse: fullHeightMeasure.implicitHeight > collapsedHeightMeasure.implicitHeight + units.gu(0.1)

    copyableText: {
        var parts = [];
        if (text)
            parts.push(text);

        if (buttonUrl)
            parts.push(buttonUrl);

        return parts.join("\n");
    }
    preferredBubbleWidth: Math.max(textMeasure.implicitWidth + units.gu(2), senderWidthHint, replyWidthHint, buttonWidthHint)

    Label {
        id: textMeasure

        visible: false
        text: root.text
        fontSize: "small"
    }

    Label {
        id: senderMeasure

        visible: false
        text: root.senderName
        fontSize: "x-small"
        font.bold: true
    }

    Label {
        id: replySenderMeasure

        visible: false
        text: root.replyToSender
        fontSize: "small"
        font.bold: true
    }

    Label {
        id: replyTextMeasure

        visible: false
        text: root.replyToText
        fontSize: "small"
    }

    Label {
        id: fullHeightMeasure

        visible: false
        text: root.text
        fontSize: "small"
        wrapMode: Text.Wrap
        width: parent.width
    }

    Label {
        id: collapsedHeightMeasure

        visible: false
        text: root.text
        fontSize: "small"
        wrapMode: Text.Wrap
        width: parent.width
        maximumLineCount: root.collapsedLineCount
        elide: Text.ElideRight
    }

    Label {
        text: root.text
        fontSize: "small"
        color: "#303030"
        wrapMode: Text.Wrap
        width: parent.width
        maximumLineCount: root.shouldCollapse && !root.expanded ? root.collapsedLineCount : 2.14748e+09
        elide: root.shouldCollapse && !root.expanded ? Text.ElideRight : Text.ElideNone
    }

    Button {
        text: root.buttonText
        width: parent.width
        visible: root.hasOpenableButton
        onClicked: Qt.openUrlExternally(root.buttonUrl)
    }

    Column {
        visible: root.shouldCollapse
        width: parent.width
        spacing: 0

        Item {
            width: 1
            height: toggleLabel.implicitHeight
        }

        Item {
            width: parent.width
            height: toggleLabel.implicitHeight + units.gu(0.6)

            Label {
                id: toggleLabel

                text: root.expanded ? i18n.tr("Show less") : i18n.tr("Show more")
                fontSize: "small"
                color: LomiriColors.blue

                anchors {
                    left: parent.left
                    verticalCenter: parent.verticalCenter
                }

            }

            MouseArea {
                anchors.fill: parent
                onClicked: root.expanded = !root.expanded
            }

        }

    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
