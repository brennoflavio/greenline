import Lomiri.Components 1.3
import QtQuick 2.7

Item {
    id: root

    property var messages: []
    property var preparedMessages: []
    property bool hasOlderMessages: false
    property bool loadingOlderMessages: false
    property string pendingRestoreMessageId: ""
    property var downloadingIds: ({
    })
    property bool isGroup: false
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

    function prepareOlderMessages(messageId) {
        pendingRestoreMessageId = messageId;
    }

    function restoreOlderMessages() {
        if (pendingRestoreMessageId === "")
            return ;

        var model = messageList.model;
        for (var i = 0; i < model.length; i++) {
            if (model[i].id === pendingRestoreMessageId) {
                messageList.positionViewAtIndex(i, ListView.End);
                break;
            }
        }
        pendingRestoreMessageId = "";
    }

    function scrollToMessage(messageId) {
        var model = messageList.model;
        for (var i = 0; i < model.length; i++) {
            if (model[i].id === messageId) {
                messageList.positionViewAtIndex(i, ListView.Center);
                return ;
            }
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

    function usesRichTextMessage(message) {
        return !!message && (!!message.reply_to_id || (root.isGroup && !message.is_outgoing && (message.sender_name || "") !== ""));
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

    onMessagesChanged: {
        var nextPrepared = messages.slice();
        nextPrepared.reverse();
        preparedMessages = nextPrepared;
    }

    ListView {
        id: messageList

        anchors.fill: parent
        clip: true
        verticalLayoutDirection: ListView.BottomToTop
        spacing: units.gu(0.5)
        model: root.preparedMessages
        onCountChanged: root.restoreOlderMessages()
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

            property var msg: modelData
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

                    property var msg: modelData

                    width: parent.width
                    sourceComponent: root.messageComponentFor(msg)
                }

            }

            leadingActions: ListItemActions {
                actions: [
                    Action {
                        iconName: "delete"
                        text: i18n.tr("Delete")
                        enabled: root.canDeleteMessage(modelData)
                        onTriggered: root.deleteRequested(modelData)
                    }
                ]
            }

            trailingActions: ListItemActions {
                actions: [
                    Action {
                        iconName: "mail-reply"
                        text: i18n.tr("Reply")
                        enabled: !!modelData && !!modelData.id && modelData.id.indexOf("pending-") !== 0
                        onTriggered: root.replyRequested(modelData)
                    },
                    Action {
                        iconName: "edit"
                        text: i18n.tr("Edit")
                        enabled: root.canEditMessage(modelData)
                        onTriggered: root.editRequested(modelData)
                    },
                    Action {
                        iconName: "like"
                        text: i18n.tr("Reactions")
                        enabled: root.canReactMessage(modelData)
                        onTriggered: root.reactionsRequested(modelData)
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
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
