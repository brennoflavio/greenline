import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string text: ""
    property string formattedText: ""
    property string buttonText: ""
    property string buttonUrl: ""
    readonly property bool hasOpenableButton: buttonText !== "" && (buttonUrl.indexOf("https://") === 0 || buttonUrl.indexOf("http://") === 0)
    readonly property real buttonWidthHint: hasOpenableButton ? units.gu(24) : 0
    readonly property string displayText: text !== "" ? text : formattedText

    copyableText: {
        var parts = [];
        if (displayText)
            parts.push(displayText);

        if (buttonUrl)
            parts.push(buttonUrl);

        return parts.join("\n");
    }
    preferredBubbleWidth: Math.max(textMeasure.implicitWidth + units.gu(2), buttonWidthHint)

    Label {
        id: textMeasure

        visible: false
        text: root.displayText
        textFormat: Text.PlainText
        fontSize: "small"
    }

    Label {
        text: root.displayText
        textFormat: Text.PlainText
        fontSize: "small"
        color: "#303030"
        wrapMode: Text.Wrap
        width: parent.width
        visible: root.displayText !== ""
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
