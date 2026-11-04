import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string question: ""
    property var options: []
    property var voteCounts: []
    property int selectableCount: 0
    property var selectedIndices: []
    property var draftSelectedIndices: []
    property string voteState: "idle"
    readonly property bool sending: voteState === "sending"
    readonly property bool submitted: voteState === "sent"

    signal voteRequested(var indices)

    readonly property bool multipleChoice: selectableCount !== 1
    readonly property bool canVote:
        !sending && !submitted &&
        question !== "" &&
        options.length > 0 &&
        draftSelectedIndices.length > 0

    preferredBubbleWidth: units.gu(30)

    Component.onCompleted: {
        draftSelectedIndices = selectedIndices.slice();
    }

    onSelectedIndicesChanged: {
        if (!sending && !submitted)
            draftSelectedIndices = selectedIndices.slice();
    }

    copyableText: question + "\n" + options.join("\n")

    function isSelected(index) {
        return draftSelectedIndices.indexOf(index) !== -1;
    }

    function toggleOption(index) {
        if (sending || submitted)
            return;

        var next = draftSelectedIndices.slice();
        var position = next.indexOf(index);

        if (position !== -1) {
            next.splice(position, 1);
        } else if (!multipleChoice) {
            next = [index];
        } else {
            if (selectableCount > 0 && next.length >= selectableCount)
                return;
            next.push(index);
        }

        draftSelectedIndices = next;
    }

    Label {
        text: root.question
        textFormat: Text.PlainText
        font.bold: true
        fontSize: "medium"
        color: "#303030"
        wrapMode: Text.Wrap
        width: parent.width
    }

    Label {
        text: root.multipleChoice
            ? i18n.tr("Select one or more options")
            : i18n.tr("Select one option")
        fontSize: "x-small"
        color: "#666666"
        width: parent.width
    }

    Repeater {
        model: root.options

        delegate: Rectangle {
            width: parent.width
            height: Math.max(optionLabel.implicitHeight + units.gu(2), units.gu(5))
            color: optionArea.pressed ? "#c5dff3" : "transparent"
            radius: units.gu(0.5)

            Row {
                spacing: units.gu(1)
                anchors {
                    left: parent.left
                    right: parent.right
                    verticalCenter: parent.verticalCenter
                    leftMargin: units.gu(0.5)
                    rightMargin: units.gu(0.5)
                }

                Label {
                    text: root.isSelected(index) ? "●" : "○"
                    color: "#2474a6"
                    width: units.gu(2.5)
                }

                Label {
                    id: optionLabel
                    text: modelData
                    textFormat: Text.PlainText
                    color: "#303030"
                    wrapMode: Text.Wrap
                    width: parent.width
                           - units.gu(3.5)
                           - (root.voteCounts.length > 0 ? units.gu(7) : 0)
                }

                Label {
                    text: root.voteCounts.length > index
                        ? String(root.voteCounts[index])
                        : ""
                    visible: root.voteCounts.length > 0
                    color: "#666666"
                    fontSize: "small"
                    horizontalAlignment: Text.AlignRight
                    width: units.gu(6)
                }
            }

            MouseArea {
                id: optionArea
                anchors.fill: parent
                enabled: !root.sending && !root.submitted
                onClicked: root.toggleOption(index)
            }
        }
    }

    Button {
        text: root.sending
            ? i18n.tr("Sending vote...")
            : root.submitted
                ? i18n.tr("Vote sent")
                : i18n.tr("Vote")
        width: parent.width
        enabled: root.canVote
        onClicked: {
            if (!root.canVote)
                return;
            root.voteRequested(root.draftSelectedIndices.slice());
        }
    }

    Item {
        width: 1
        height: units.gu(1.5)
    }
}
