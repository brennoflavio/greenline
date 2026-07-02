import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string text: ""
    property string formattedText: ""
    property string buttonText: ""
    property string buttonUrl: ""
    readonly property bool hasOpenableButton: buttonText !== "" && (buttonUrl.indexOf("https://") === 0 || buttonUrl.indexOf("http://") === 0)
    readonly property real senderWidthHint: showSender ? senderMeasure.implicitWidth + units.gu(2) : 0
    readonly property real replyWidthHint: replyToId !== "" ? Math.max(replySenderMeasure.implicitWidth, replyTextMeasure.implicitWidth) + units.gu(3.5) : 0
    readonly property real buttonWidthHint: hasOpenableButton ? units.gu(24) : 0
    readonly property bool usesFormattedText: formattedText !== ""
    readonly property string displayText: usesFormattedText ? formattedText : text
    readonly property string plainDisplayText: usesFormattedText ? formattedText.replace(/<br\s*\/?>/gi, "\n").replace(/<\/p>/gi, "\n").replace(/<\/div>/gi, "\n").replace(/<\/li>/gi, "\n").replace(/<[^>]*>/g, " ").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">") : text

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
        text: root.plainDisplayText
        textFormat: Text.PlainText
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
        textFormat: Text.PlainText
        fontSize: "small"
    }

    Label {
        text: root.displayText
        textFormat: root.usesFormattedText ? Text.RichText : Text.PlainText
        onLinkActivated: Qt.openUrlExternally(link)
        fontSize: "small"
        color: "#303030"
        wrapMode: Text.Wrap
        width: parent.width
    }

    Button {
        text: root.buttonText
        width: parent.width
        visible: root.hasOpenableButton
        onClicked: Qt.openUrlExternally(root.buttonUrl)
    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
