import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import Lomiri.Content 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7
import QtQuick.Layouts 1.3
import UserMetrics 0.1
import "components"
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: chatPage

    property string chatId: ""
    property string chatName: ""
    property string chatPhoto: ""
    property bool isGroup: false
    property var messages: []
    property var downloadingIds: ({
    })
    property int unreadCount: 0
    property string chatStatus: ""
    property string presenceStatus: ""
    property var activeTypers: ({
    })
    property string replyToMessageId: ""
    property string replyToSender: ""
    property string replyToText: ""
    property string replyToParticipant: ""

    function messagePreview(message) {
        if (!message)
            return "";

        if (message.text)
            return message.text;

        if (message.caption)
            return message.caption;

        if (message.type === "contact")
            return "👤 " + (message.file_name || i18n.tr("Contact"));

        var previews = {
            "image": "📷 Photo",
            "image_gallery": "📷 Photo",
            "video": "🎥 Video",
            "audio": "🎵 Audio",
            "voice": "🎵 Audio",
            "document": "📄 Document",
            "sticker": "🏷️ Sticker",
            "link_preview": "🔗 Link"
        };
        return previews[message.type] || message.type || "";
    }

    function contactNameFromPath(filePath) {
        var cleanPath = filePath.toString().replace("file://", "");
        var parts = cleanPath.split("/");
        var name = parts.length > 0 ? parts[parts.length - 1] : "";
        var dotIndex = name.lastIndexOf(".");
        if (dotIndex > 0)
            name = name.slice(0, dotIndex);

        return name || i18n.tr("Contact");
    }

    function canReplyToMessage(message) {
        return !!message && !!message.id && message.id.indexOf("pending-") !== 0;
    }

    function currentReplyContext() {
        if (replyToMessageId === "")
            return null;

        return {
            "id": replyToMessageId,
            "sender": replyToSender,
            "text": replyToText,
            "participant": replyToParticipant
        };
    }

    function clearReply() {
        replyToMessageId = "";
        replyToSender = "";
        replyToText = "";
        replyToParticipant = "";
    }

    function consumeReplyContext() {
        var replyContext = currentReplyContext();
        clearReply();
        return replyContext;
    }

    function startReply(message) {
        if (!canReplyToMessage(message))
            return ;

        replyToMessageId = message.id;
        replyToSender = message.is_outgoing ? i18n.tr("You") : (message.sender_name || chatName || message.sender || "");
        replyToText = messagePreview(message);
        replyToParticipant = message.is_outgoing ? "" : (message.sender || "");
        messageInput.forceActiveFocus();
    }

    function scrollToMessage(messageId) {
        var model = messageList.model;
        for (var i = 0; i < model.length; i++) {
            if (model[i].id === messageId) {
                messageList.positionViewAtIndex(i, ListView.Center);
                return ;
            }
        }
    }

    function triggerDownload(messageId, mediaType) {
        var d = downloadingIds;
        d[messageId] = true;
        downloadingIds = d;
        messagesChanged();
        python.call('main.download_media', [chatId, messageId, mediaType], function(result) {
            var d2 = downloadingIds;
            delete d2[messageId];
            downloadingIds = d2;
            messagesChanged();
        });
    }

    function sendVideoMessage(filePath) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var hours = now.getHours().toString();
        if (hours.length < 2)
            hours = "0" + hours;

        var minutes = now.getMinutes().toString();
        if (minutes.length < 2)
            minutes = "0" + minutes;

        var replyContext = consumeReplyContext();
        var pendingMsg = {
            "id": tempId,
            "chat_id": chatId,
            "type": "video",
            "is_outgoing": true,
            "text": "",
            "caption": "",
            "timestamp": hours + ":" + minutes,
            "read_receipt": "",
            "send_status": "pending",
            "temp_id": tempId,
            "media_path": "file://" + filePath,
            "reply_to_id": replyContext ? replyContext.id : "",
            "reply_to_sender": replyContext ? replyContext.sender : "",
            "reply_to_text": replyContext ? replyContext.text : ""
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesChanged();
        python.call('main.send_video_message', [chatId, filePath, "", tempId, replyContext], function() {
        });
    }

    function sendStickerMessage(filePath) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var hours = now.getHours().toString();
        if (hours.length < 2)
            hours = "0" + hours;

        var minutes = now.getMinutes().toString();
        if (minutes.length < 2)
            minutes = "0" + minutes;

        var replyContext = consumeReplyContext();
        var pendingMsg = {
            "id": tempId,
            "chat_id": chatId,
            "type": "sticker",
            "is_outgoing": true,
            "text": "",
            "caption": "",
            "timestamp": hours + ":" + minutes,
            "read_receipt": "",
            "send_status": "pending",
            "temp_id": tempId,
            "media_path": filePath,
            "reply_to_id": replyContext ? replyContext.id : "",
            "reply_to_sender": replyContext ? replyContext.sender : "",
            "reply_to_text": replyContext ? replyContext.text : ""
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesChanged();
        var cleanPath = filePath.toString().replace("file://", "");
        python.call('main.send_sticker_message', [chatId, cleanPath, tempId, replyContext], function() {
        });
    }

    function sendImageMessage(filePath) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var hours = now.getHours().toString();
        if (hours.length < 2)
            hours = "0" + hours;

        var minutes = now.getMinutes().toString();
        if (minutes.length < 2)
            minutes = "0" + minutes;

        var replyContext = consumeReplyContext();
        var pendingMsg = {
            "id": tempId,
            "chat_id": chatId,
            "type": "image",
            "is_outgoing": true,
            "text": "",
            "caption": "",
            "timestamp": hours + ":" + minutes,
            "read_receipt": "",
            "send_status": "pending",
            "temp_id": tempId,
            "media_path": "file://" + filePath,
            "reply_to_id": replyContext ? replyContext.id : "",
            "reply_to_sender": replyContext ? replyContext.sender : "",
            "reply_to_text": replyContext ? replyContext.text : ""
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesChanged();
        python.call('main.send_image_message', [chatId, filePath, "", tempId, replyContext], function() {
        });
    }

    function sendContactMessage(filePath) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var hours = now.getHours().toString();
        if (hours.length < 2)
            hours = "0" + hours;

        var minutes = now.getMinutes().toString();
        if (minutes.length < 2)
            minutes = "0" + minutes;

        var replyContext = consumeReplyContext();
        var pendingMsg = {
            "id": tempId,
            "chat_id": chatId,
            "type": "contact",
            "is_outgoing": true,
            "text": "",
            "timestamp": hours + ":" + minutes,
            "read_receipt": "",
            "send_status": "pending",
            "temp_id": tempId,
            "file_name": contactNameFromPath(filePath),
            "media_path": "file://" + filePath,
            "reply_to_id": replyContext ? replyContext.id : "",
            "reply_to_sender": replyContext ? replyContext.sender : "",
            "reply_to_text": replyContext ? replyContext.text : ""
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesChanged();
        python.call('main.send_contact_message', [chatId, filePath, tempId, replyContext], function(result) {
            if (result && !result.success)
                toast.show(result.message || i18n.tr("Failed to send contact"));

        });
    }

    function sendMessage() {
        Qt.inputMethod.commit();
        if (messageInput.text.length > 0) {
            var text = messageInput.text;
            var tempId = "pending-" + Date.now();
            var now = new Date();
            var hours = now.getHours().toString();
            if (hours.length < 2)
                hours = "0" + hours;

            var minutes = now.getMinutes().toString();
            if (minutes.length < 2)
                minutes = "0" + minutes;

            var replyContext = consumeReplyContext();
            var pendingMsg = {
                "id": tempId,
                "chat_id": chatId,
                "type": "text",
                "is_outgoing": true,
                "text": text,
                "timestamp": hours + ":" + minutes,
                "read_receipt": "",
                "send_status": "pending",
                "temp_id": tempId,
                "reply_to_id": replyContext ? replyContext.id : "",
                "reply_to_sender": replyContext ? replyContext.sender : "",
                "reply_to_text": replyContext ? replyContext.text : ""
            };
            var newMessages = messages.slice();
            newMessages.push(pendingMsg);
            messages = newMessages;
            messagesChanged();
            messageInput.text = "";
            python.call('main.send_text_message', [chatId, text, tempId, replyContext], function() {
            });
        }
    }

    Timer {
        id: typingTimer

        interval: 5000
        repeat: false
        onTriggered: {
            activeTypers = {
            };
            chatStatus = presenceStatus;
        }
    }

    Metric {
        id: messagesReadMetric

        name: "greenline_messages_read"
        format: "%1 " + i18n.tr("WhatsApp messages read today")
        emptyFormat: i18n.tr("No WhatsApp messages read today")
        domain: "greenline.brennoflavio"
    }

    ListView {
        id: messageList

        clip: true
        verticalLayoutDirection: ListView.BottomToTop
        spacing: units.gu(0.5)
        model: messages.slice().reverse()
        onAtYEndChanged: {
            if (atYEnd)
                chatPage.unreadCount = 0;

        }

        anchors {
            top: chatHeader.bottom
            left: parent.left
            right: parent.right
            bottom: inputBar.top
        }

        delegate: ListItem {
            id: messageDelegate

            width: parent ? parent.width : 0
            height: messageLoader.item ? messageLoader.item.height : 0
            color: "transparent"
            highlightColor: "transparent"
            divider.visible: false

            Loader {
                id: messageLoader

                property var msg: modelData

                width: parent.width
                sourceComponent: {
                    if (msg.type === "text")
                        return textComponent;

                    if (msg.type === "image")
                        return imageComponent;

                    if (msg.type === "image_gallery")
                        return galleryComponent;

                    if (msg.type === "video")
                        return videoComponent;

                    if (msg.type === "voice" || msg.type === "audio")
                        return voiceComponent;

                    if (msg.type === "document")
                        return documentComponent;

                    if (msg.type === "contact")
                        return contactComponent;

                    if (msg.type === "sticker")
                        return stickerComponent;

                    if (msg.type === "link_preview")
                        return linkPreviewComponent;

                    return textComponent;
                }
            }

            trailingActions: ListItemActions {
                actions: [
                    Action {
                        iconName: "mail-reply"
                        text: i18n.tr("Reply")
                        enabled: chatPage.canReplyToMessage(modelData)
                        onTriggered: chatPage.startReply(modelData)
                    },
                    Action {
                        iconName: "edit-copy"
                        text: i18n.tr("Copy")
                        enabled: messageLoader.item && messageLoader.item.copyableText
                        onTriggered: {
                            Clipboard.push(messageLoader.item.copyableText);
                            toast.show(i18n.tr("Copied to clipboard"));
                        }
                    }
                ]
            }

        }

    }

    Component {
        id: textComponent

        TextMessage {
            text: msg.text || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
        }

    }

    Component {
        id: imageComponent

        ImageMessage {
            imageSource: msg.image_source || ""
            thumbnailSource: msg.thumbnail_path || ""
            mediaPath: msg.media_path || ""
            caption: msg.caption || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
            downloading: downloadingIds[msg.id] || false
            onDownloadRequested: triggerDownload(msg.id, "image")
        }

    }

    Component {
        id: galleryComponent

        ImageGalleryMessage {
            images: msg.images || []
            caption: msg.caption || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
        }

    }

    Component {
        id: videoComponent

        VideoMessage {
            thumbnailSource: msg.thumbnail_path || ""
            mediaPath: msg.media_path || ""
            caption: msg.caption || ""
            duration: msg.duration || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
            downloading: downloadingIds[msg.id] || false
            onDownloadRequested: triggerDownload(msg.id, "video")
        }

    }

    Component {
        id: voiceComponent

        VoiceMessage {
            duration: msg.duration || "0:00"
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
            downloading: downloadingIds[msg.id] || false
            onDownloadRequested: triggerDownload(msg.id, "audio")
        }

    }

    Component {
        id: documentComponent

        DocumentMessage {
            fileName: msg.file_name || ""
            caption: msg.caption || ""
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
            downloading: downloadingIds[msg.id] || false
            onDownloadRequested: triggerDownload(msg.id, "document")
        }

    }

    Component {
        id: contactComponent

        ContactMessage {
            contactName: msg.file_name || ""
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
        }

    }

    Component {
        id: linkPreviewComponent

        LinkPreviewMessage {
            text: msg.text || ""
            linkTitle: msg.link_title || ""
            linkDescription: msg.link_description || ""
            linkUrl: msg.link_url || ""
            thumbnailSource: msg.thumbnail_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
        }

    }

    Component {
        id: stickerComponent

        StickerMessage {
            stickerSource: msg.sticker_source || ""
            thumbnailSource: msg.thumbnail_path || ""
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: chatPage.isGroup
            timestamp: msg.timestamp || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: scrollToMessage(messageId)
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
            bottom: inputBar.top
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
            visible: chatPage.unreadCount > 0
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
                text: chatPage.unreadCount
                fontSize: "x-small"
                font.weight: Font.Medium
                color: "white"
            }

        }

        MouseArea {
            anchors.fill: parent
            onClicked: messageList.positionViewAtIndex(0, ListView.End)
        }

        Behavior on opacity {
            NumberAnimation {
                duration: 150
            }

        }

    }

    Toast {
        id: toast
    }

    KeyboardSpacer {
        id: keyboardSpacer

        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

    }

    Rectangle {
        id: inputBar

        height: inputColumn.implicitHeight + units.gu(2)
        color: theme.palette.normal.background

        anchors {
            left: parent.left
            right: parent.right
            bottom: keyboardSpacer.top
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
                margins: units.gu(1)
            }

            Rectangle {
                width: parent.width
                height: replyPreviewColumn.height + units.gu(1)
                radius: units.gu(0.6)
                color: theme.palette.normal.base
                visible: chatPage.replyToMessageId !== ""

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
                        text: chatPage.replyToSender
                        fontSize: "small"
                        font.bold: true
                        color: LomiriColors.blue
                        elide: Text.ElideRight
                        width: parent.width
                    }

                    Label {
                        text: chatPage.replyToText
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
                        onClicked: clearReply()
                    }

                }

            }

            RowLayout {
                id: inputRowLayout

                width: parent.width
                spacing: units.gu(1)

                Icon {
                    id: attachmentIcon

                    name: "attachment"
                    width: units.gu(3)
                    height: units.gu(3)
                    color: theme.palette.normal.backgroundSecondaryText
                    Layout.alignment: Qt.AlignVCenter

                    MouseArea {
                        anchors.fill: parent
                        onClicked: PopupUtils.open(attachmentDialog)
                    }

                }

                TextArea {
                    id: messageInput

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    placeholderText: i18n.tr("Type a message...")
                    autoSize: true
                    maximumLineCount: 5
                }

                Icon {
                    name: "send"
                    width: units.gu(3)
                    height: units.gu(3)
                    color: LomiriColors.green
                    Layout.alignment: Qt.AlignVCenter

                    MouseArea {
                        anchors.fill: parent
                        onClicked: sendMessage()
                    }

                }

            }

        }

    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                python.call('main.get_messages', [chatId], function(result) {
                    if (result.success) {
                        messages = result.messages;
                        if (unreadCount > 0)
                            messagesReadMetric.increment(unreadCount);

                        python.call('main.mark_messages_as_read', [chatId], function() {
                        });
                    }
                });
                if (!isGroup)
                    python.call('main.subscribe_presence', [chatId], function() {
                });

                setHandler('message-upsert', function(incomingMessages) {
                    var updated = messages.slice();
                    var hasNewIncoming = false;
                    for (var i = 0; i < incomingMessages.length; i++) {
                        var message = incomingMessages[i];
                        if (message.chat_id !== chatId)
                            continue;

                        var found = false;
                        for (var j = 0; j < updated.length; j++) {
                            if (updated[j].id === message.id || (message.temp_id && updated[j].id === message.temp_id)) {
                                updated[j] = message;
                                found = true;
                                break;
                            }
                        }
                        if (!found) {
                            updated.push(message);
                            if (!message.is_outgoing) {
                                hasNewIncoming = true;
                                if (!messageList.atYEnd)
                                    chatPage.unreadCount += 1;

                            }
                        }
                    }
                    messages = updated;
                    messagesChanged();
                    if (hasNewIncoming) {
                        messagesReadMetric.increment(1);
                        python.call('main.mark_messages_as_read', [chatId], function() {
                        });
                    }
                });
                setHandler('presence-update', function(presenceList) {
                    for (var i = 0; i < presenceList.length; i++) {
                        if (presenceList[i].jid === chatId) {
                            presenceStatus = presenceList[i].status;
                            if (!typingTimer.running)
                                chatStatus = presenceStatus;

                            break;
                        }
                    }
                });
                setHandler('chat-presence', function(chatPresenceList) {
                    var typers = activeTypers;
                    for (var i = 0; i < chatPresenceList.length; i++) {
                        var entry = chatPresenceList[i];
                        if (entry.chat === chatId) {
                            if (entry.state === "composing")
                                typers[entry.sender] = entry.media === "audio" ? "audio" : "typing";
                            else
                                delete typers[entry.sender];
                        }
                    }
                    activeTypers = typers;
                    var keys = Object.keys(activeTypers);
                    if (keys.length > 0) {
                        var hasAudio = false;
                        for (var j = 0; j < keys.length; j++) {
                            if (activeTypers[keys[j]] === "audio") {
                                hasAudio = true;
                                break;
                            }
                        }
                        chatStatus = hasAudio ? i18n.tr("recording audio...") : i18n.tr("typing...");
                        typingTimer.restart();
                    } else {
                        typingTimer.stop();
                        chatStatus = presenceStatus;
                    }
                });
                setHandler('sender-photo-update', function(photoList) {
                    var changed = false;
                    var updated = messages.slice();
                    for (var i = 0; i < photoList.length; i++) {
                        var entry = photoList[i];
                        for (var j = 0; j < updated.length; j++) {
                            if (updated[j].sender === entry.jid) {
                                updated[j] = Object.assign({
                                }, updated[j], {
                                    "sender_photo": entry.photo
                                });
                                changed = true;
                            }
                        }
                    }
                    if (changed) {
                        messages = updated;
                        messagesChanged();
                    }
                });
            });
        }
    }

    ContentStore {
        id: contentStore

        scope: ContentScope.App
    }

    Component {
        id: attachmentDialog

        Dialog {
            id: attachDialog

            title: i18n.tr("Send Attachment")

            Button {
                text: i18n.tr("Photo")
                onClicked: {
                    PopupUtils.close(attachDialog);
                    pageStack.push(mediaPickerPage);
                }
            }

            Button {
                text: i18n.tr("Video")
                onClicked: {
                    PopupUtils.close(attachDialog);
                    pageStack.push(videoPickerPage);
                }
            }

            Button {
                text: i18n.tr("Sticker")
                onClicked: {
                    PopupUtils.close(attachDialog);
                    pageStack.push(stickerPickerComponent);
                }
            }

            Button {
                text: i18n.tr("Contact")
                onClicked: {
                    PopupUtils.close(attachDialog);
                    pageStack.push(contactPickerPage);
                }
            }

            Button {
                text: i18n.tr("Cancel")
                color: theme.palette.normal.base
                onClicked: PopupUtils.close(attachDialog)
            }

        }

    }

    Component {
        id: mediaPickerPage

        Page {
            id: pickerPageInstance

            property var activeTransfer

            ContentPeerPicker {
                contentType: ContentType.Pictures
                handler: ContentHandler.Source
                onPeerSelected: {
                    pickerPageInstance.activeTransfer = peer.request(contentStore);
                    pickerPageInstance.activeTransfer.selectionType = ContentTransfer.Single;
                    pickerPageInstance.activeTransfer.stateChanged.connect(function() {
                        if (pickerPageInstance.activeTransfer.state === ContentTransfer.Charged) {
                            if (pickerPageInstance.activeTransfer.items.length > 0) {
                                var fileUrl = pickerPageInstance.activeTransfer.items[0].url.toString();
                                var filePath = fileUrl.replace("file://", "");
                                pageStack.pop();
                                sendImageMessage(filePath);
                            }
                        }
                    });
                }
                onCancelPressed: {
                    if (pickerPageInstance.activeTransfer)
                        pickerPageInstance.activeTransfer.state = ContentTransfer.Aborted;

                    pageStack.pop();
                }

                anchors {
                    top: pickerHeader.bottom
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }

            }

            header: PageHeader {
                id: pickerHeader

                title: i18n.tr("Send Photo")
                leadingActionBar.actions: [
                    Action {
                        iconName: "back"
                        onTriggered: {
                            if (pickerPageInstance.activeTransfer)
                                pickerPageInstance.activeTransfer.state = ContentTransfer.Aborted;

                            pageStack.pop();
                        }
                    }
                ]
            }

        }

    }

    Component {
        id: videoPickerPage

        Page {
            id: videoPickerPageInstance

            property var activeTransfer

            ContentPeerPicker {
                contentType: ContentType.Videos
                handler: ContentHandler.Source
                onPeerSelected: {
                    videoPickerPageInstance.activeTransfer = peer.request(contentStore);
                    videoPickerPageInstance.activeTransfer.selectionType = ContentTransfer.Single;
                    videoPickerPageInstance.activeTransfer.stateChanged.connect(function() {
                        if (videoPickerPageInstance.activeTransfer.state === ContentTransfer.Charged) {
                            if (videoPickerPageInstance.activeTransfer.items.length > 0) {
                                var fileUrl = videoPickerPageInstance.activeTransfer.items[0].url.toString();
                                var filePath = fileUrl.replace("file://", "");
                                pageStack.pop();
                                sendVideoMessage(filePath);
                            }
                        }
                    });
                }
                onCancelPressed: {
                    if (videoPickerPageInstance.activeTransfer)
                        videoPickerPageInstance.activeTransfer.state = ContentTransfer.Aborted;

                    pageStack.pop();
                }

                anchors {
                    top: videoPickerHeader.bottom
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }

            }

            header: PageHeader {
                id: videoPickerHeader

                title: i18n.tr("Send Video")
                leadingActionBar.actions: [
                    Action {
                        iconName: "back"
                        onTriggered: {
                            if (videoPickerPageInstance.activeTransfer)
                                videoPickerPageInstance.activeTransfer.state = ContentTransfer.Aborted;

                            pageStack.pop();
                        }
                    }
                ]
            }

        }

    }

    Component {
        id: contactPickerPage

        Page {
            id: contactPickerPageInstance

            property var activeTransfer

            ContentPeerPicker {
                contentType: ContentType.Contacts
                handler: ContentHandler.Source
                onPeerSelected: {
                    contactPickerPageInstance.activeTransfer = peer.request(contentStore);
                    contactPickerPageInstance.activeTransfer.selectionType = ContentTransfer.Single;
                    contactPickerPageInstance.activeTransfer.stateChanged.connect(function() {
                        if (contactPickerPageInstance.activeTransfer.state === ContentTransfer.Charged) {
                            if (contactPickerPageInstance.activeTransfer.items.length > 0) {
                                var fileUrl = contactPickerPageInstance.activeTransfer.items[0].url.toString();
                                var filePath = fileUrl.replace("file://", "");
                                pageStack.pop();
                                sendContactMessage(filePath);
                            }
                        }
                    });
                }
                onCancelPressed: {
                    if (contactPickerPageInstance.activeTransfer)
                        contactPickerPageInstance.activeTransfer.state = ContentTransfer.Aborted;

                    pageStack.pop();
                }

                anchors {
                    top: contactPickerHeader.bottom
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }

            }

            header: PageHeader {
                id: contactPickerHeader

                title: i18n.tr("Send Contact")
                leadingActionBar.actions: [
                    Action {
                        iconName: "back"
                        onTriggered: {
                            if (contactPickerPageInstance.activeTransfer)
                                contactPickerPageInstance.activeTransfer.state = ContentTransfer.Aborted;

                            pageStack.pop();
                        }
                    }
                ]
            }

        }

    }

    Component {
        id: stickerPickerComponent

        StickerPickerPage {
            onStickerSelected: sendStickerMessage(filePath)
        }

    }

    header: PageHeader {
        id: chatHeader

        leadingActionBar.actions: [
            Action {
                iconName: "back"
                text: i18n.tr("Back")
                onTriggered: pageStack.pop()
            }
        ]

        contents: Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: units.gu(1.5)

            Rectangle {
                width: units.gu(4.5)
                height: units.gu(4.5)
                radius: width / 2
                color: theme.palette.normal.base
                anchors.verticalCenter: parent.verticalCenter

                Image {
                    id: headerAvatar

                    anchors.fill: parent
                    source: chatPhoto || ""
                    fillMode: Image.PreserveAspectCrop
                    visible: false
                }

                Rectangle {
                    id: headerAvatarMask

                    anchors.fill: parent
                    radius: width / 2
                    visible: false
                }

                OpacityMask {
                    anchors.fill: parent
                    source: headerAvatar
                    maskSource: headerAvatarMask
                    visible: !!chatPhoto
                }

                Icon {
                    anchors.centerIn: parent
                    name: "contact"
                    width: units.gu(2.5)
                    height: units.gu(2.5)
                    color: theme.palette.normal.backgroundSecondaryText
                    visible: !chatPhoto
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        pageStack.push(Qt.resolvedUrl("ProfilePage.qml"), {
                            "chatId": chatId,
                            "chatName": chatName,
                            "chatPhoto": chatPhoto
                        });
                    }
                }

            }

            Column {
                anchors.verticalCenter: parent.verticalCenter

                Label {
                    text: chatName
                    fontSize: "medium"
                    font.bold: true
                }

                Label {
                    text: chatStatus
                    fontSize: "x-small"
                    color: theme.palette.normal.backgroundTertiaryText
                    visible: chatStatus !== ""
                }

            }

        }

    }

}
