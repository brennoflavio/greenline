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
        chatComposer.focusInput();
    }

    function scrollToMessage(messageId) {
        chatMessageList.scrollToMessage(messageId);
    }

    function triggerDownload(messageId, mediaType) {
        var d = Object.assign({
        }, downloadingIds);
        d[messageId] = true;
        downloadingIds = d;
        python.call('main.download_media', [chatId, messageId, mediaType], function(result) {
            var d2 = Object.assign({
            }, downloadingIds);
            delete d2[messageId];
            downloadingIds = d2;
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
        python.call('main.send_contact_message', [chatId, filePath, tempId, replyContext], function(result) {
            if (result && !result.success)
                toast.show(result.message || i18n.tr("Failed to send contact"));

        });
    }

    function sendMessage() {
        Qt.inputMethod.commit();
        if (chatComposer.text.length > 0) {
            var text = chatComposer.text;
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
            chatComposer.text = "";
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

    ChatMessageList {
        id: chatMessageList

        messages: chatPage.messages
        downloadingIds: chatPage.downloadingIds
        isGroup: chatPage.isGroup
        unreadCount: chatPage.unreadCount
        onBottomReached: chatPage.unreadCount = 0
        onReplyRequested: chatPage.startReply(message)
        onCopyRequested: {
            Clipboard.push(text);
            toast.show(i18n.tr("Copied to clipboard"));
        }
        onDownloadRequested: chatPage.triggerDownload(messageId, mediaType)

        anchors {
            top: chatHeader.bottom
            left: parent.left
            right: parent.right
            bottom: chatComposer.top
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

    ChatComposer {
        id: chatComposer

        replyToMessageId: chatPage.replyToMessageId
        replyToSender: chatPage.replyToSender
        replyToText: chatPage.replyToText
        onClearReplyRequested: chatPage.clearReply()
        onAttachmentRequested: PopupUtils.open(attachmentDialog)
        onSendRequested: chatPage.sendMessage()

        anchors {
            left: parent.left
            right: parent.right
            bottom: keyboardSpacer.top
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
                                if (!chatMessageList.atBottom)
                                    chatPage.unreadCount += 1;

                            }
                        }
                    }
                    messages = updated;
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
                    var typers = Object.assign({
                    }, activeTypers);
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
                    if (changed)
                        messages = updated;

                });
            });
        }
    }

    Component {
        id: attachmentDialog

        ChatAttachmentDialog {
            onPhotoRequested: pageStack.push(mediaPickerPage)
            onVideoRequested: pageStack.push(videoPickerPage)
            onStickerRequested: pageStack.push(stickerPickerComponent)
            onContactRequested: pageStack.push(contactPickerPage)
        }

    }

    Component {
        id: mediaPickerPage

        ChatAttachmentPickerPage {
            pickerTitle: i18n.tr("Send Photo")
            pickerContentType: ContentType.Pictures
            onFileSelected: sendImageMessage(filePath)
        }

    }

    Component {
        id: videoPickerPage

        ChatAttachmentPickerPage {
            pickerTitle: i18n.tr("Send Video")
            pickerContentType: ContentType.Videos
            onFileSelected: sendVideoMessage(filePath)
        }

    }

    Component {
        id: contactPickerPage

        ChatAttachmentPickerPage {
            pickerTitle: i18n.tr("Send Contact")
            pickerContentType: ContentType.Contacts
            onFileSelected: sendContactMessage(filePath)
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
