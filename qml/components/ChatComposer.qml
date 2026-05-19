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
    property bool suggestionPointerDown: false
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
        root.mentionSpans = validateMentionSpans(messageInput.text, nextMentionSpans);
        syncingMentionState = false;
    }

    function clearMentionSuggestions() {
        activeMentionStart = -1;
        activeMentionQuery = "";
        filteredMentionCandidates = [];
    }

    function cloneSpan(span) {
        return {
            "jid": String(span.jid || ""),
            "label": String(span.label || ""),
            "start": Number(span.start || 0),
            "length": Number(span.length || 0)
        };
    }

    function isMentionBoundaryChar(character) {
        return character === "" || !/[0-9A-Za-z_]/.test(character);
    }

    function validateMentionSpans(currentText, spans) {
        if (!currentText || !spans || !spans.length)
            return [];

        var prepared = [];
        for (var i = 0; i < spans.length; i++) {
            var span = spans[i];
            if (!span)
                continue;

            var label = String(span.label || "");
            var jid = String(span.jid || "");
            var start = Number(span.start);
            var length = Number(span.length);
            var token = "@" + label;
            var end = start + length;
            var before = start > 0 ? currentText.charAt(start - 1) : "";
            var after = end < currentText.length ? currentText.charAt(end) : "";
            if (!jid || !label || start < 0 || length <= 0)
                continue;

            if (length !== token.length || end > currentText.length || currentText.slice(start, end) !== token)
                continue;

            if (!isMentionBoundaryChar(before) || !isMentionBoundaryChar(after))
                continue;

            prepared.push({
                "jid": jid,
                "label": label,
                "start": start,
                "length": length,
                "order": i
            });
        }
        prepared.sort(function(a, b) {
            if (a.start === b.start)
                return a.order - b.order;

            return a.start - b.start;
        });
        var validated = [];
        var lastEnd = -1;
        for (var j = 0; j < prepared.length; j++) {
            var preparedSpan = prepared[j];
            if (preparedSpan.start < lastEnd)
                continue;

            validated.push({
                "jid": preparedSpan.jid,
                "label": preparedSpan.label,
                "start": preparedSpan.start,
                "length": preparedSpan.length
            });
            lastEnd = preparedSpan.start + preparedSpan.length;
        }
        return validated;
    }

    function updateMentionSpansForEdit(oldText, newText) {
        if (!root.mentionSpans.length)
            return [];

        var prefixLength = 0;
        while (prefixLength < oldText.length && prefixLength < newText.length && oldText.charAt(prefixLength) === newText.charAt(prefixLength))prefixLength++
        var suffixLength = 0;
        while (suffixLength < oldText.length - prefixLength && suffixLength < newText.length - prefixLength && oldText.charAt(oldText.length - 1 - suffixLength) === newText.charAt(newText.length - 1 - suffixLength))suffixLength++
        var oldChangeEnd = oldText.length - suffixLength;
        var shift = newText.length - oldText.length;
        var shifted = [];
        for (var i = 0; i < root.mentionSpans.length; i++) {
            var span = cloneSpan(root.mentionSpans[i]);
            var spanEnd = span.start + span.length;
            if (spanEnd <= prefixLength) {
                shifted.push(span);
                continue;
            }
            if (span.start >= oldChangeEnd) {
                span.start += shift;
                shifted.push(span);
            }
        }
        return validateMentionSpans(newText, shifted);
    }

    function updateMentionSuggestions() {
        var cursor = messageInput.cursorPosition;
        var textBeforeCursor = messageInput.text.slice(0, cursor);
        var atIndex = textBeforeCursor.lastIndexOf("@");
        if (atIndex < 0) {
            clearMentionSuggestions();
            return ;
        }
        if (atIndex > 0 && !/\s/.test(textBeforeCursor.charAt(atIndex - 1))) {
            clearMentionSuggestions();
            return ;
        }
        var query = textBeforeCursor.slice(atIndex + 1);
        if (/\s/.test(query)) {
            clearMentionSuggestions();
            return ;
        }
        activeMentionStart = atIndex;
        activeMentionQuery = query;
        var queryLower = query.toLowerCase();
        var matches = [];
        for (var i = 0; i < root.mentionCandidates.length; i++) {
            var candidate = root.mentionCandidates[i];
            var label = String(candidate && candidate.label || "");
            if (!label)
                continue;

            if (queryLower === "" || label.toLowerCase().indexOf(queryLower) !== -1)
                matches.push(candidate);

        }
        filteredMentionCandidates = matches.slice(0, 5);
    }

    function insertMention(candidate) {
        var label = String(candidate && candidate.label || "");
        var jid = String(candidate && candidate.jid || "");
        if (!label || !jid || activeMentionStart < 0)
            return ;

        var cursor = messageInput.cursorPosition;
        var replacement = "@" + label + " ";
        var before = messageInput.text.slice(0, activeMentionStart);
        var after = messageInput.text.slice(cursor);
        var newText = before + replacement + after;
        var shift = replacement.length - (cursor - activeMentionStart);
        var nextSpans = [];
        for (var i = 0; i < root.mentionSpans.length; i++) {
            var span = cloneSpan(root.mentionSpans[i]);
            var spanEnd = span.start + span.length;
            if (spanEnd <= activeMentionStart) {
                nextSpans.push(span);
                continue;
            }
            if (span.start >= cursor) {
                span.start += shift;
                nextSpans.push(span);
            }
        }
        nextSpans.push({
            "jid": jid,
            "label": label,
            "start": activeMentionStart,
            "length": replacement.length - 1
        });
        nextSpans = validateMentionSpans(newText, nextSpans);
        suppressTextTracking = true;
        messageInput.text = newText;
        messageInput.cursorPosition = before.length + replacement.length;
        suppressTextTracking = false;
        previousText = newText;
        setMentionSpans(nextSpans);
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

        Rectangle {
            id: replyPreview

            width: parent.width
            height: replyPreviewColumn.height + units.gu(1)
            radius: units.gu(0.6)
            color: theme.palette.normal.base
            visible: root.replyToMessageId !== ""

            Rectangle {
                width: units.gu(0.3)
                height: parent.height
                radius: units.gu(0.15)
                color: LomiriColors.blue
            }

            Column {
                id: replyPreviewColumn

                spacing: units.gu(0.1)

                anchors {
                    left: parent.left
                    right: clearReplyIcon.left
                    top: parent.top
                    leftMargin: units.gu(0.8)
                    rightMargin: units.gu(0.6)
                    topMargin: units.gu(0.5)
                }

                Label {
                    text: root.replyToSender
                    fontSize: "small"
                    font.bold: true
                    color: LomiriColors.blue
                    elide: Text.ElideRight
                    width: parent.width
                }

                Label {
                    text: root.replyToText
                    fontSize: "small"
                    color: theme.palette.normal.backgroundSecondaryText
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    wrapMode: Text.NoWrap
                    width: parent.width
                }

            }

            Icon {
                id: clearReplyIcon

                name: "close"
                width: units.gu(2.2)
                height: units.gu(2.2)
                color: theme.palette.normal.backgroundSecondaryText

                anchors {
                    right: parent.right
                    rightMargin: units.gu(0.8)
                    verticalCenter: parent.verticalCenter
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: root.clearReplyRequested()
                }

            }

        }

        Rectangle {
            id: mentionSuggestions

            width: parent.width
            height: Math.min(filteredMentionCandidates.length, 4) * units.gu(5)
            radius: units.gu(0.6)
            color: theme.palette.normal.base
            border.width: units.dp(1)
            border.color: theme.palette.normal.backgroundSecondaryText
            visible: filteredMentionCandidates.length > 0 && activeMentionStart >= 0
            clip: true

            ListView {
                anchors.fill: parent
                model: filteredMentionCandidates
                interactive: filteredMentionCandidates.length > 4

                delegate: ListItem {
                    width: parent ? parent.width : mentionSuggestions.width
                    height: units.gu(5)
                    divider.visible: index < filteredMentionCandidates.length - 1

                    MouseArea {
                        anchors.fill: parent
                        onPressed: root.suggestionPointerDown = true
                        onCanceled: root.suggestionPointerDown = false
                        onReleased: root.suggestionPointerDown = false
                        onClicked: root.insertMention(modelData)
                    }

                    Row {
                        spacing: units.gu(1)

                        anchors {
                            left: parent.left
                            leftMargin: units.gu(1)
                            right: parent.right
                            rightMargin: units.gu(1)
                            verticalCenter: parent.verticalCenter
                        }

                        Rectangle {
                            width: units.gu(3.2)
                            height: units.gu(3.2)
                            radius: width / 2
                            color: theme.palette.normal.background
                            visible: !candidatePhoto.visible

                            Label {
                                anchors.centerIn: parent
                                text: String(modelData && modelData.label || "").slice(0, 1).toUpperCase()
                                font.bold: true
                                color: theme.palette.normal.backgroundText
                            }

                        }

                        Image {
                            id: candidatePhoto

                            width: units.gu(3.2)
                            height: units.gu(3.2)
                            fillMode: Image.PreserveAspectCrop
                            source: String(modelData && modelData.photo || "")
                            visible: source !== ""
                        }

                        Label {
                            width: parent.width - units.gu(5.5)
                            text: String(modelData && modelData.label || "")
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }

                    }

                }

            }

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
                    setMentionSpans(updateMentionSpansForEdit(previousText, text));
                    previousText = text;
                    updateMentionSuggestions();
                }
                onCursorPositionChanged: updateMentionSuggestions()
                onActiveFocusChanged: {
                    if (!activeFocus && !root.suggestionPointerDown && !mentionSuggestions.visible)
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
