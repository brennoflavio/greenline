import "../lib/ChatHelpers.js" as ChatHelpers
import Lomiri.Components 1.3
import QtQuick 2.7

Item {
    id: root

    property var messages: []
    property var senderMetadataByJid: ({
    })
    property bool hasOlderMessages: false
    property bool loadingOlderMessages: false
    property string pendingRestoreMessageId: ""
    property var downloadingIds: ({
    })
    property bool isGroup: false
    property var messageIndexesById: ({
    })
    property var messageIndexesByTempId: ({
    })
    property int unreadCount: 0
    property string unreadDividerMessageId: ""
    property int editWindowSeconds: 20 * 60
    readonly property bool atBottom: messageList.atYEnd

    signal replyRequested(var message)
    signal editRequested(var message)
    signal deleteRequested(var message)
    signal reactionsRequested(var message)
    signal copyRequested(string text)
    signal downloadRequested(string messageId, string mediaType)
    signal bottomReached()
    signal olderMessagesRequested()
    signal messageNotLoaded(string messageId)

    function messageAt(index) {
        if (index < 0 || index >= messageModel.count)
            return null;

        return messageModel.get(index).message;
    }

    function clearMessageIndexes() {
        messageIndexesById = ({
        });
        messageIndexesByTempId = ({
        });
    }

    function setMessageIndex(message, index) {
        if (!message)
            return ;

        if (message.id)
            messageIndexesById[message.id] = index;

        if (message.temp_id)
            messageIndexesByTempId[message.temp_id] = index;

    }

    function removeMessageIndex(message) {
        if (!message)
            return ;

        if (message.id)
            delete messageIndexesById[message.id];

        if (message.temp_id)
            delete messageIndexesByTempId[message.temp_id];

    }

    function refreshMessageIndexes(startIndex) {
        for (var i = startIndex; i < messageModel.count; i++) {
            var modelMessage = messageAt(i);
            if (!modelMessage)
                continue;

            if (modelMessage.id)
                messageIndexesById[modelMessage.id] = i;

            if (modelMessage.temp_id)
                messageIndexesByTempId[modelMessage.temp_id] = i;

        }
    }

    function findModelIndexById(messageId) {
        if (!messageId)
            return -1;

        return messageIndexesById.hasOwnProperty(messageId) ? messageIndexesById[messageId] : -1;
    }

    function findModelIndexByIdOrTempId(messageId, tempId) {
        if (messageId !== "") {
            if (messageIndexesById.hasOwnProperty(messageId))
                return messageIndexesById[messageId];

            if (messageIndexesByTempId.hasOwnProperty(messageId))
                return messageIndexesByTempId[messageId];

        }
        if (tempId !== "") {
            if (messageIndexesById.hasOwnProperty(tempId))
                return messageIndexesById[tempId];

            if (messageIndexesByTempId.hasOwnProperty(tempId))
                return messageIndexesByTempId[tempId];

        }
        return -1;
    }

    function findDisplayInsertIndex(message) {
        for (var i = 0; i < messageModel.count; i++) {
            var existingMessage = messageAt(i);
            if (ChatHelpers.messageComesBefore(existingMessage, message))
                return i;

        }
        return messageModel.count;
    }

    function insertDisplayMessage(message) {
        var wasAtBottom = messageList.atYEnd;
        var insertIndex = findDisplayInsertIndex(message);
        messageModel.insert(insertIndex, {
            "message": message
        });
        refreshMessageIndexes(insertIndex);
        if (wasAtBottom && insertIndex === 0)
            scrollToBottomTimer.restart();

        return insertIndex;
    }

    function setMessageAt(index, message) {
        if (index < 0 || index >= messageModel.count)
            return false;

        var previousMessage = messageAt(index);
        if (previousMessage)
            removeMessageIndex(previousMessage);

        messageModel.set(index, {
            "message": message
        });
        setMessageIndex(message, index);
        return true;
    }

    function prepareOlderMessages(messageId) {
        pendingRestoreMessageId = messageId;
    }

    function restoreOlderMessages() {
        if (pendingRestoreMessageId === "")
            return ;

        var restoreIndex = findModelIndexById(pendingRestoreMessageId);
        if (restoreIndex !== -1)
            messageList.positionViewAtIndex(restoreIndex, ListView.End);

        pendingRestoreMessageId = "";
    }

    function scheduleRestoreOlderMessages() {
        if (pendingRestoreMessageId === "")
            return ;

        restoreOlderMessagesTimer.restart();
    }

    function resetMessages(oldestFirstMessages) {
        messageModel.clear();
        clearMessageIndexes();
        var nextMessages = oldestFirstMessages || [];
        for (var i = nextMessages.length - 1; i >= 0; i--) {
            messageModel.append({
                "message": nextMessages[i]
            });
            setMessageIndex(nextMessages[i], nextMessages.length - 1 - i);
        }
    }

    function appendPendingMessage(message) {
        insertDisplayMessage(message);
        scrollToBottomTimer.restart();
    }

    function replaceMessageByIdOrTempId(message) {
        if (!message)
            return -1;

        var wasAtBottom = messageList.atYEnd;
        var replaceIndex = findModelIndexByIdOrTempId(message.id || "", message.temp_id || "");
        if (replaceIndex !== -1) {
            var previousMessage = messageAt(replaceIndex);
            removeMessageIndex(previousMessage);
            messageModel.remove(replaceIndex);
            refreshMessageIndexes(replaceIndex);
        }
        var insertIndex = insertDisplayMessage(message);
        if (wasAtBottom)
            scrollToBottomTimer.restart();

        return insertIndex;
    }

    function patchMessageAtIndex(index, patch) {
        var currentMessage = messageAt(index);
        if (!currentMessage)
            return false;

        return setMessageAt(index, Object.assign({
        }, currentMessage, patch));
    }

    function patchMessageByIdOrTempId(messageId, tempId, patch) {
        var patchIndex = findModelIndexByIdOrTempId(messageId || "", tempId || "");
        if (patchIndex === -1)
            return false;

        return patchMessageAtIndex(patchIndex, patch);
    }

    function upsertMessages(messagesToUpsert) {
        var nextMessages = messagesToUpsert || [];
        for (var i = 0; i < nextMessages.length; i++) {
            if (nextMessages[i])
                replaceMessageByIdOrTempId(nextMessages[i]);

        }
    }

    function appendOlderMessages(olderMessages, anchorMessageId) {
        var nextMessages = olderMessages || [];
        if (anchorMessageId)
            prepareOlderMessages(anchorMessageId);

        var appendStartIndex = messageModel.count;
        for (var i = nextMessages.length - 1; i >= 0; i--) {
            messageModel.append({
                "message": nextMessages[i]
            });
            setMessageIndex(nextMessages[i], appendStartIndex + (nextMessages.length - 1 - i));
        }
        scheduleRestoreOlderMessages();
    }

    function scrollToMessage(messageId) {
        var scrollIndex = findModelIndexById(messageId);
        if (scrollIndex !== -1) {
            messageList.positionViewAtIndex(scrollIndex, ListView.Center);
            return ;
        }
        messageNotLoaded(messageId);
    }

    function scrollToBottom() {
        messageList.positionViewAtBeginning();
    }

    function messageText(message) {
        var type = message.type || "";
        if (type === "deleted")
            return i18n.tr("Deleted message");

        if (type === "view_once")
            return i18n.tr("View-once message. Open WhatsApp on your primary device to view it.");

        return message.text || "";
    }

    function formattedMessageText(message) {
        return message.formatted_text || "";
    }

    function canEditMessage(message) {
        var messageId = message && message.id ? message.id : "";
        var timestampUnix = message && message.timestamp_unix ? message.timestamp_unix : 0;
        var mentionedJids = message && message.mentioned_jids ? message.mentioned_jids : [];
        var mentionSpans = message && message.mention_spans ? message.mention_spans : [];
        return !!message && !!message.is_outgoing && messageId !== "" && messageId.indexOf("pending-") !== 0 && messageId.indexOf("failed-") !== 0 && (message.type || "") === "text" && mentionedJids.length === 0 && mentionSpans.length === 0 && timestampUnix > 0 && Math.floor(Date.now() / 1000) - timestampUnix <= editWindowSeconds;
    }

    function canDeleteMessage(message) {
        var messageId = message && message.id ? message.id : "";
        var sendStatus = message && message.send_status ? message.send_status : "";
        return !!message && !!message.is_outgoing && messageId !== "" && messageId.indexOf("pending-") !== 0 && messageId.indexOf("failed-") !== 0 && sendStatus !== "pending" && sendStatus !== "failed" && (message.type || "") !== "deleted";
    }

    function canReactMessage(message) {
        var messageId = message && message.id ? message.id : "";
        var sendStatus = message && message.send_status ? message.send_status : "";
        return !!message && messageId !== "" && messageId.indexOf("pending-") !== 0 && messageId.indexOf("failed-") !== 0 && sendStatus !== "pending" && sendStatus !== "failed" && (message.type || "") !== "deleted";
    }

    function senderMetadataForJid(jid) {
        if (!jid || !senderMetadataByJid.hasOwnProperty(jid))
            return null;

        return senderMetadataByJid[jid];
    }

    function resolvedSenderName(message) {
        if (!message || message.is_outgoing)
            return "";

        var metadata = senderMetadataForJid(message.sender || "");
        if (metadata && metadata.name)
            return metadata.name;

        if (message.sender_name)
            return message.sender_name;

        return message.sender || "";
    }

    function resolvedSenderPhoto(message) {
        if (!message)
            return "";

        var metadata = senderMetadataForJid(message.sender || "");
        if (metadata && metadata.hasOwnProperty("photo"))
            return metadata.photo || "";

        return message.sender_photo || "";
    }

    function resolvedReplyToSender(message) {
        if (!message)
            return "";

        if (message.reply_to_from_me)
            return i18n.tr("You");

        var metadata = senderMetadataForJid(message.reply_to_sender_id || "");
        if (metadata && metadata.name)
            return metadata.name;

        return message.reply_to_sender || "";
    }

    function usesRichTextMessage(message) {
        return !!message && (!!message.reply_to_id || (root.isGroup && !message.is_outgoing) || (message.text_render_mode || "simple") === "rich");
    }

    function messageComponentFor(message) {
        var type = message && message.type ? message.type : "text";
        if (type === "text" || type === "view_once" || type === "deleted")
            return root.usesRichTextMessage(message) ? richTextComponent : textComponent;

        if (type === "image")
            return imageComponent;

        if (type === "video")
            return videoComponent;

        if (type === "audio")
            return voiceComponent;

        if (type === "document")
            return documentComponent;

        if (type === "contact")
            return contactComponent;

        if (type === "location")
            return locationComponent;

        if (type === "sticker")
            return stickerComponent;

        if (type === "link_preview")
            return linkPreviewComponent;

        return root.usesRichTextMessage(message) ? richTextComponent : textComponent;
    }

    onMessagesChanged: root.resetMessages(messages)

    Timer {
        id: restoreOlderMessagesTimer

        interval: 0
        repeat: false
        onTriggered: root.restoreOlderMessages()
    }

    Timer {
        id: scrollToBottomTimer

        interval: 0
        repeat: false
        onTriggered: root.scrollToBottom()
    }

    ListModel {
        id: messageModel
    }

    ListView {
        id: messageList

        anchors.fill: parent
        clip: true
        cacheBuffer: units.gu(100)
        verticalLayoutDirection: ListView.BottomToTop
        spacing: units.gu(0.5)
        model: messageModel
        onMovementEnded: {
            if (atYBeginning && root.hasOlderMessages && !root.loadingOlderMessages)
                root.olderMessagesRequested();

        }
        onAtYEndChanged: {
            if (atYEnd)
                root.bottomReached();

        }

        delegate: ListItem {
            id: messageDelegate

            property var msg: message
            property bool showUnreadDivider: root.unreadDividerMessageId !== "" && msg && msg.id === root.unreadDividerMessageId

            width: parent ? parent.width : 0
            height: messageContent.height
            color: "transparent"
            highlightColor: "transparent"
            divider.visible: false

            Column {
                id: messageContent

                width: parent.width
                spacing: units.gu(0.8)

                Item {
                    visible: messageDelegate.showUnreadDivider
                    width: parent.width
                    height: visible ? units.gu(3) : 0

                    Rectangle {
                        height: units.dp(1)
                        color: theme.palette.normal.foregroundText

                        anchors {
                            left: parent.left
                            right: unreadLabel.left
                            leftMargin: units.gu(1.5)
                            rightMargin: units.gu(1)
                            verticalCenter: unreadLabel.verticalCenter
                        }

                    }

                    Label {
                        id: unreadLabel

                        text: i18n.tr("Unread")
                        color: theme.palette.normal.foregroundText
                        fontSize: "small"
                        anchors.centerIn: parent
                    }

                    Rectangle {
                        height: units.dp(1)
                        color: theme.palette.normal.foregroundText

                        anchors {
                            left: unreadLabel.right
                            right: parent.right
                            leftMargin: units.gu(1)
                            rightMargin: units.gu(1.5)
                            verticalCenter: unreadLabel.verticalCenter
                        }

                    }

                }

                Loader {
                    id: messageLoader

                    property var msg: messageDelegate.msg

                    function syncSourceComponent() {
                        var nextComponent = root.messageComponentFor(msg);
                        if (sourceComponent !== nextComponent)
                            sourceComponent = nextComponent;

                    }

                    width: parent.width
                    Component.onCompleted: syncSourceComponent()
                    onMsgChanged: syncSourceComponent()

                    Connections {
                        target: root
                        onIsGroupChanged: messageLoader.syncSourceComponent()
                    }

                }

            }

            leadingActions: ListItemActions {
                actions: [
                    Action {
                        iconName: "delete"
                        text: i18n.tr("Delete")
                        enabled: root.canDeleteMessage(messageDelegate.msg)
                        onTriggered: root.deleteRequested(messageDelegate.msg)
                    }
                ]
            }

            trailingActions: ListItemActions {
                actions: [
                    Action {
                        iconName: "mail-reply"
                        text: i18n.tr("Reply")
                        enabled: !!messageDelegate.msg && !!messageDelegate.msg.id && messageDelegate.msg.id.indexOf("pending-") !== 0
                        onTriggered: root.replyRequested(messageDelegate.msg)
                    },
                    Action {
                        iconName: "edit"
                        text: i18n.tr("Edit")
                        enabled: root.canEditMessage(messageDelegate.msg)
                        onTriggered: root.editRequested(messageDelegate.msg)
                    },
                    Action {
                        iconName: "like"
                        text: i18n.tr("Reactions")
                        enabled: root.canReactMessage(messageDelegate.msg)
                        onTriggered: root.reactionsRequested(messageDelegate.msg)
                    },
                    Action {
                        iconName: "edit-copy"
                        text: i18n.tr("Copy")
                        enabled: messageLoader.item && messageLoader.item.copyableText
                        onTriggered: root.copyRequested(messageLoader.item.copyableText)
                    }
                ]
            }

        }

    }

    Component {
        id: textComponent

        TextMessage {
            text: root.messageText(msg)
            formattedText: root.formattedMessageText(msg)
            buttonText: msg.button_text || ""
            buttonUrl: msg.button_url || ""
            isOutgoing: msg.is_outgoing || false
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
        }

    }

    Component {
        id: richTextComponent

        RichTextMessage {
            text: root.messageText(msg)
            formattedText: root.formattedMessageText(msg)
            buttonText: msg.button_text || ""
            buttonUrl: msg.button_url || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
        }

    }

    Component {
        id: imageComponent

        ImageMessage {
            imageSource: msg.image_source || ""
            thumbnailSource: msg.thumbnail_path || ""
            mediaPath: msg.media_path || ""
            caption: msg.caption || ""
            formattedCaption: msg.formatted_caption || ""
            buttonText: msg.button_text || ""
            buttonUrl: msg.button_url || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
            downloading: root.downloadingIds[msg.id] || false
            onDownloadRequested: root.downloadRequested(msg.id, "image")
        }

    }

    Component {
        id: videoComponent

        VideoMessage {
            thumbnailSource: msg.thumbnail_path || ""
            mediaPath: msg.media_path || ""
            caption: msg.caption || ""
            formattedCaption: msg.formatted_caption || ""
            duration: msg.duration || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
            downloading: root.downloadingIds[msg.id] || false
            onDownloadRequested: root.downloadRequested(msg.id, "video")
        }

    }

    Component {
        id: voiceComponent

        VoiceMessage {
            duration: msg.duration || "0:00"
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
            downloading: root.downloadingIds[msg.id] || false
            onDownloadRequested: root.downloadRequested(msg.id, "audio")
        }

    }

    Component {
        id: documentComponent

        DocumentMessage {
            fileName: msg.file_name || ""
            caption: msg.caption || ""
            formattedCaption: msg.formatted_caption || ""
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
            downloading: root.downloadingIds[msg.id] || false
            onDownloadRequested: root.downloadRequested(msg.id, "document")
        }

    }

    Component {
        id: contactComponent

        ContactMessage {
            contactName: msg.file_name || ""
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
        }

    }

    Component {
        id: locationComponent

        LocationMessage {
            title: msg.text || ""
            detail: msg.caption || ""
            linkUrl: msg.link_url || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
        }

    }

    Component {
        id: linkPreviewComponent

        LinkPreviewMessage {
            text: msg.text || ""
            formattedText: msg.formatted_text || ""
            linkTitle: msg.link_title || ""
            linkDescription: msg.link_description || ""
            linkUrl: msg.link_url || ""
            thumbnailSource: msg.thumbnail_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
        }

    }

    Component {
        id: stickerComponent

        StickerMessage {
            stickerSource: msg.sticker_source || ""
            thumbnailSource: msg.thumbnail_path || ""
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            timestampUnix: msg.timestamp_unix || 0
            edited: msg.edited || false
            hasReactions: msg.has_reactions || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: root.resolvedSenderName(msg)
            senderPhoto: root.resolvedSenderPhoto(msg)
            replyToId: msg.reply_to_id || ""
            replyToSender: root.resolvedReplyToSender(msg)
            replyToText: msg.reply_to_text || ""
            formattedReplyToText: msg.formatted_reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
        }

    }

    Rectangle {
        id: scrollToBottomButton

        width: units.gu(4.5)
        height: units.gu(4.5)
        radius: width / 2
        color: Qt.rgba(0, 0, 0, 0.6)
        visible: !messageList.atYEnd
        opacity: visible ? 1 : 0
        z: 1

        anchors {
            right: parent.right
            rightMargin: units.gu(2)
            bottom: parent.bottom
            bottomMargin: units.gu(1.5)
        }

        Icon {
            anchors.centerIn: parent
            name: "down"
            width: units.gu(2.5)
            height: units.gu(2.5)
            color: "white"
        }

        Rectangle {
            visible: root.unreadCount > 0
            width: Math.max(units.gu(2.5), badgeLabel.implicitWidth + units.gu(1))
            height: units.gu(2.5)
            radius: height / 2
            color: LomiriColors.green
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.top
            anchors.bottomMargin: units.gu(0.3)

            Label {
                id: badgeLabel

                anchors.centerIn: parent
                text: root.unreadCount
                fontSize: "x-small"
                font.weight: Font.Medium
                color: "white"
            }

        }

        MouseArea {
            anchors.fill: parent
            onClicked: root.scrollToBottom()
        }

        Behavior on opacity {
            NumberAnimation {
                duration: 150
            }

        }

    }

}
