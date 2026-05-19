import "../lib/MentionHelpers.js" as MentionHelpers
import Lomiri.Components 1.3
import QtQuick 2.7

Rectangle {
    id: root

    property string replyToMessageId: ""
    property string replyToSender: ""
    property string replyToText: ""
    property var mentionCandidates: []
    property var mentionSpans: []
    property alias text: messageInput.text
    property var filteredMentionCandidates: []
    property string activeMentionQuery: ""
    property int activeMentionStart: -1
    property bool syncingMentionState: false
    property bool suppressTextTracking: false
    property string previousText: ""

    signal clearReplyRequested()
    signal attachmentRequested()
    signal sendRequested()

    function focusInput() {
        messageInput.forceActiveFocus();
    }

    function setTextAndMentions(nextText, nextMentionSpans) {
        suppressTextTracking = true;
        messageInput.text = nextText || "";
        suppressTextTracking = false;
        previousText = messageInput.text;
        setMentionSpans(nextMentionSpans);
        updateMentionSuggestions();
    }

    function setMentionSpans(nextMentionSpans) {
        syncingMentionState = true;
        root.mentionSpans = MentionHelpers.validateMentionSpans(messageInput.text, nextMentionSpans);
        syncingMentionState = false;
    }

    function clearMentionSuggestions() {
        activeMentionStart = -1;
        activeMentionQuery = "";
        filteredMentionCandidates = [];
    }

    function applyMentionSuggestionState(state) {
        activeMentionStart = state.activeMentionStart;
        activeMentionQuery = state.activeMentionQuery;
        filteredMentionCandidates = state.filteredMentionCandidates;
    }

    function updateMentionSuggestions() {
        applyMentionSuggestionState(MentionHelpers.mentionSuggestions(messageInput.text, messageInput.cursorPosition, root.mentionCandidates, 5));
    }

    function insertMention(candidate) {
        var result = MentionHelpers.insertMention(messageInput.text, messageInput.cursorPosition, activeMentionStart, root.mentionSpans, candidate);
        suppressTextTracking = true;
        messageInput.text = result.text;
        messageInput.cursorPosition = result.cursorPosition;
        suppressTextTracking = false;
        previousText = result.text;
        setMentionSpans(result.mentionSpans);
        clearMentionSuggestions();
        messageInput.forceActiveFocus();
    }

    height: inputRow.height + units.gu(2) + (replyPreview.visible ? replyPreview.height + inputColumn.spacing : 0) + (mentionSuggestions.visible ? mentionSuggestions.height + inputColumn.spacing : 0)
    color: theme.palette.normal.background
    Component.onCompleted: {
        previousText = messageInput.text;
        setMentionSpans(root.mentionSpans);
    }
    onMentionCandidatesChanged: updateMentionSuggestions()
    onMentionSpansChanged: {
        if (!syncingMentionState)
            setMentionSpans(root.mentionSpans);

    }

    Rectangle {
        height: units.dp(1)
        color: theme.palette.normal.base

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
        }

    }

    Column {
        id: inputColumn

        spacing: units.gu(0.5)

        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            topMargin: units.gu(1)
            leftMargin: units.gu(1)
            rightMargin: units.gu(1)
        }

        ChatComposerReplyPreview {
            id: replyPreview

            width: parent.width
            visible: root.replyToMessageId !== ""
            sender: root.replyToSender
            previewText: root.replyToText
            onClearRequested: root.clearReplyRequested()
        }

        ChatComposerMentionSuggestions {
            id: mentionSuggestions

            width: parent.width
            visible: filteredMentionCandidates.length > 0 && activeMentionStart >= 0
            candidates: filteredMentionCandidates
            onCandidateSelected: root.insertMention(candidate)
        }

        Item {
            id: inputRow

            width: parent.width
            height: Math.max(messageInput.height, attachmentIcon.height, sendIcon.height)

            Icon {
                id: attachmentIcon

                name: "attachment"
                width: units.gu(3)
                height: units.gu(3)
                color: theme.palette.normal.backgroundSecondaryText

                anchors {
                    left: parent.left
                    verticalCenter: messageInput.verticalCenter
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.attachmentRequested()
                }

            }

            Icon {
                id: sendIcon

                name: "send"
                width: units.gu(3)
                height: units.gu(3)
                color: LomiriColors.green

                anchors {
                    right: parent.right
                    verticalCenter: messageInput.verticalCenter
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.sendRequested()
                }

            }

            TextArea {
                id: messageInput

                placeholderText: i18n.tr("Type a message...")
                autoSize: true
                maximumLineCount: 5
                onTextChanged: {
                    if (suppressTextTracking) {
                        previousText = text;
                        return ;
                    }
                    setMentionSpans(MentionHelpers.updateMentionSpansForEdit(previousText, text, root.mentionSpans));
                    previousText = text;
                    updateMentionSuggestions();
                }
                onCursorPositionChanged: updateMentionSuggestions()
                onActiveFocusChanged: {
                    if (!activeFocus && !mentionSuggestions.suggestionPointerDown && !mentionSuggestions.visible)
                        clearMentionSuggestions();

                }

                anchors {
                    left: attachmentIcon.right
                    right: sendIcon.left
                    verticalCenter: parent.verticalCenter
                    leftMargin: units.gu(1)
                    rightMargin: units.gu(1)
                }

            }

        }

    }

}
