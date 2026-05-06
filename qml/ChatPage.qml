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
    property int messagePageSize: 50
    property string nextMessagesCursor: ""
    property bool hasOlderMessages: false
    property bool loadingOlderMessages: false
    property var downloadingIds: ({
    })
    property int initialUnreadCount: 0
    property int unreadCount: 0
    property string chatStatus: ""
    property string presenceStatus: ""
    property var activeTypers: ({
    })
    property string replyToMessageId: ""
    property string replyToSender: ""
    property string replyToText: ""
    property string replyToParticipant: ""
    property bool pythonReady: false
    property bool refreshInProgress: false
    property bool refreshQueued: false
    property bool draftLoaded: false
    property bool draftTouchedBeforeLoad: false
    property bool draftSaveInFlight: false
    property string lastSavedDraftText: ""
    property string pendingDraftText: ""

    function messagePreview(message) {
        if (!message)
            return "";

        if (message.type === "view_once")
            return i18n.tr("View-once message. Open WhatsApp on your primary device to view it.");

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

    function perfLog(message) {
        console.log("[ChatPage perf][" + chatId + "][" + Date.now() + "] " + message);
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

    function messageComesBefore(left, right) {
        var leftTimestamp = left && left.timestamp_unix ? left.timestamp_unix : 0;
        var rightTimestamp = right && right.timestamp_unix ? right.timestamp_unix : 0;
        if (leftTimestamp !== rightTimestamp)
            return leftTimestamp < rightTimestamp;

        var leftId = left && left.id ? left.id : "";
        var rightId = right && right.id ? right.id : "";
        return leftId < rightId;
    }

    function insertMessageSorted(messageList, message) {
        for (var i = 0; i < messageList.length; i++) {
            if (messageComesBefore(message, messageList[i])) {
                messageList.splice(i, 0, message);
                return ;
            }
        }
        messageList.push(message);
    }

    function loadInitialMessages() {
        var startedAt = Date.now();
        perfLog("loadInitialMessages start pageSize=" + messagePageSize);
        python.call('main.get_messages', [chatId, "", messagePageSize], function(result) {
            perfLog("loadInitialMessages done ms=" + (Date.now() - startedAt) + " success=" + (!!result && result.success) + " messages=" + ((result && result.messages) ? result.messages.length : 0) + " hasMore=" + (!!result && result.has_more));
            if (result && result.success) {
                nextMessagesCursor = result.next_cursor || "";
                hasOlderMessages = !!result.has_more;
                messages = result.messages;
                var unreadOnOpen = initialUnreadCount;
                if (unreadOnOpen > 0) {
                    initialUnreadCount = 0;
                    messagesReadMetric.increment(unreadOnOpen);
                    python.call('main.mark_messages_as_read', [chatId], function() {
                    });
                }
            }
        });
    }

    function loadDraft() {
        python.call('main.get_chat_draft', [chatId], function(result) {
            var draftText = result && result.success ? (result.text || "") : "";
            if (!draftTouchedBeforeLoad && (chatComposer.text || "") === "") {
                lastSavedDraftText = draftText;
                pendingDraftText = draftText;
                draftLoaded = true;
                chatComposer.text = draftText;
                return ;
            }
            if (pendingDraftText === draftText && !draftSaveInFlight)
                lastSavedDraftText = draftText;

            draftLoaded = true;
            if (pendingDraftText !== lastSavedDraftText)
                saveDraft(pendingDraftText);

        });
    }

    function saveDraft(text) {
        if (!pythonReady)
            return ;

        pendingDraftText = text;
        if (!draftLoaded && !draftTouchedBeforeLoad)
            return ;

        if (draftSaveInFlight)
            return ;

        if (pendingDraftText === lastSavedDraftText)
            return ;

        var textToSave = pendingDraftText;
        draftSaveInFlight = true;
        python.call('main.set_chat_draft', [chatId, textToSave], function(result) {
            draftSaveInFlight = false;
            if (result && result.success)
                lastSavedDraftText = textToSave;

            if (pendingDraftText !== textToSave)
                saveDraft(pendingDraftText);

        });
    }

    function flushDraft() {
        draftSaveTimer.stop();
        saveDraft(chatComposer.text || "");
    }

    function isLocalOnlyMessage(message) {
        var messageId = message && message.id ? message.id : "";
        return messageId.indexOf("pending-") === 0 || messageId.indexOf("failed-") === 0 || message.send_status === "pending" || message.send_status === "failed";
    }

    function mergeRefreshedMessages(refreshedMessages) {
        var mergedMessages = refreshedMessages.slice();
        var knownIds = {
        };
        var knownTempIds = {
        };
        for (var i = 0; i < refreshedMessages.length; i++) {
            var refreshed = refreshedMessages[i];
            if (refreshed.id)
                knownIds[refreshed.id] = true;

            if (refreshed.temp_id)
                knownTempIds[refreshed.temp_id] = true;

        }
        var oldestRefreshed = refreshedMessages.length > 0 ? refreshedMessages[0] : null;
        for (var j = 0; j < messages.length; j++) {
            var existing = messages[j];
            var existingId = existing.id || "";
            var existingTempId = existing.temp_id || "";
            if ((existingId !== "" && (knownIds[existingId] || knownTempIds[existingId])) || (existingTempId !== "" && (knownIds[existingTempId] || knownTempIds[existingTempId])))
                continue;

            if (isLocalOnlyMessage(existing) || (oldestRefreshed && messageComesBefore(existing, oldestRefreshed)))
                insertMessageSorted(mergedMessages, existing);

        }
        return mergedMessages;
    }

    function refreshPageState(reason) {
        function finishRefresh() {
            pendingCallbacks -= 1;
            if (pendingCallbacks === 0) {
                var queued = refreshQueued;
                refreshInProgress = false;
                perfLog("refreshPageState done reason=" + reason + " totalMs=" + (Date.now() - refreshStartedAt) + " queued=" + queued + " messagesNow=" + messages.length);
                if (queued)
                    refreshPageState("queued-after-" + reason);

            }
        }

        reason = reason || "unknown";
        var refreshStartedAt = Date.now();
        var chatInfoStartedAt = 0;
        var messagesStartedAt = 0;
        if (!pythonReady) {
            perfLog("refreshPageState skipped reason=" + reason + " pythonReady=false");
            return ;
        }
        if (refreshInProgress) {
            refreshQueued = true;
            perfLog("refreshPageState queued reason=" + reason + " currentMessages=" + messages.length);
            return ;
        }
        refreshInProgress = true;
        refreshQueued = false;
        var pendingCallbacks = 2;
        var wasAtBottom = chatMessageList.atBottom;
        perfLog("refreshPageState start reason=" + reason + " currentMessages=" + messages.length + " atBottom=" + wasAtBottom);
        chatInfoStartedAt = Date.now();
        python.call('main.get_chat_info', [chatId], function(result) {
            perfLog("refreshPageState chatInfo done reason=" + reason + " ms=" + (Date.now() - chatInfoStartedAt) + " success=" + (!!result && result.success) + " unread=" + ((result && result.unread_count) ? result.unread_count : 0));
            if (result && result.success) {
                chatName = result.name || chatName;
                chatPhoto = result.photo || "";
                isGroup = !!result.is_group;
                if (wasAtBottom) {
                    if (result.unread_count > 0) {
                        unreadCount = 0;
                        messagesReadMetric.increment(result.unread_count);
                        python.call('main.mark_messages_as_read', [chatId], function() {
                        });
                    }
                } else {
                    unreadCount = result.unread_count || 0;
                }
            }
            finishRefresh();
        });
        messagesStartedAt = Date.now();
        python.call('main.get_messages', [chatId, "", messagePageSize], function(result) {
            perfLog("refreshPageState messages done reason=" + reason + " ms=" + (Date.now() - messagesStartedAt) + " success=" + (!!result && result.success) + " returned=" + ((result && result.messages) ? result.messages.length : 0));
            if (result && result.success) {
                nextMessagesCursor = result.next_cursor || "";
                hasOlderMessages = !!result.has_more;
                messages = mergeRefreshedMessages(result.messages || []);
                if (wasAtBottom)
                    chatMessageList.scrollToBottom();

            }
            finishRefresh();
        });
    }

    function loadOlderMessages() {
        if (loadingOlderMessages || !hasOlderMessages || nextMessagesCursor === "")
            return ;

        loadingOlderMessages = true;
        var anchorMessageId = messages.length > 0 ? messages[0].id : "";
        python.call('main.get_messages', [chatId, nextMessagesCursor, messagePageSize], function(result) {
            loadingOlderMessages = false;
            if (!result || !result.success) {
                toast.show(result && result.message ? result.message : i18n.tr("Failed to load older messages"));
                return ;
            }
            nextMessagesCursor = result.next_cursor || "";
            hasOlderMessages = !!result.has_more;
            if (!result.messages || result.messages.length === 0)
                return ;

            if (anchorMessageId !== "")
                chatMessageList.prepareOlderMessages(anchorMessageId);

            messages = result.messages.concat(messages);
        });
    }

    function sendVideoMessage(filePath) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var timestampUnix = Math.floor(now.getTime() / 1000);
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
            "timestamp_unix": timestampUnix,
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
        messagesSendAttemptsMetric.increment(1);
        python.call('main.send_video_message', [chatId, filePath, "", tempId, replyContext], function() {
        });
    }

    function sendStickerMessage(filePath) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var timestampUnix = Math.floor(now.getTime() / 1000);
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
            "timestamp_unix": timestampUnix,
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
        messagesSendAttemptsMetric.increment(1);
        var cleanPath = filePath.toString().replace("file://", "");
        python.call('main.send_sticker_message', [chatId, cleanPath, tempId, replyContext], function() {
        });
    }

    function sendImageMessage(filePath) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var timestampUnix = Math.floor(now.getTime() / 1000);
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
            "timestamp_unix": timestampUnix,
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
        messagesSendAttemptsMetric.increment(1);
        python.call('main.send_image_message', [chatId, filePath, "", tempId, replyContext], function() {
        });
    }

    function sendContactMessage(filePath) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var timestampUnix = Math.floor(now.getTime() / 1000);
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
            "timestamp_unix": timestampUnix,
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
        messagesSendAttemptsMetric.increment(1);
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
            var timestampUnix = Math.floor(now.getTime() / 1000);
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
                "timestamp_unix": timestampUnix,
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
            messagesSendAttemptsMetric.increment(1);
            chatComposer.text = "";
            draftSaveTimer.stop();
            saveDraft("");
            python.call('main.send_text_message', [chatId, text, tempId, replyContext], function() {
            });
        }
    }

    Component.onDestruction: flushDraft()

    Timer {
        id: draftSaveTimer

        interval: 500
        repeat: false
        onTriggered: chatPage.saveDraft(chatComposer.text || "")
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

    Metric {
        id: messagesSendAttemptsMetric

        name: "greenline_messages_send_attempts"
        format: "%1 " + i18n.tr("WhatsApp messages sent today")
        emptyFormat: i18n.tr("No WhatsApp messages sent today")
        domain: "greenline.brennoflavio"
    }

    ChatMessageList {
        id: chatMessageList

        messages: chatPage.messages
        hasOlderMessages: chatPage.hasOlderMessages
        loadingOlderMessages: chatPage.loadingOlderMessages
        downloadingIds: chatPage.downloadingIds
        isGroup: chatPage.isGroup
        unreadCount: chatPage.unreadCount
        onBottomReached: {
            if (chatPage.unreadCount > 0) {
                var unreadWhileAway = chatPage.unreadCount;
                chatPage.unreadCount = 0;
                messagesReadMetric.increment(unreadWhileAway);
                python.call('main.mark_messages_as_read', [chatId], function() {
                });
            }
        }
        onOlderMessagesRequested: chatPage.loadOlderMessages()
        onMessageNotLoaded: toast.show(i18n.tr("Scroll up to load older messages first"))
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
        onTextChanged: {
            chatPage.pendingDraftText = chatComposer.text || "";
            if (!chatPage.draftLoaded)
                chatPage.draftTouchedBeforeLoad = true;

            draftSaveTimer.restart();
        }
        onClearReplyRequested: chatPage.clearReply()
        onAttachmentRequested: PopupUtils.open(attachmentDialog)
        onSendRequested: chatPage.sendMessage()

        anchors {
            left: parent.left
            right: parent.right
            bottom: keyboardSpacer.top
        }

    }

    Connections {
        target: Qt.application
        onStateChanged: {
            if (Qt.application.state === Qt.ApplicationActive)
                refreshPageState("app-active");
            else
                flushDraft();
        }
    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                pythonReady = true;
                loadInitialMessages();
                loadDraft();
                if (!isGroup)
                    python.call('main.subscribe_presence', [chatId], function() {
                });

                setHandler('message-upsert', function(incomingMessages) {
                    var updated = messages.slice();
                    var wasAtBottom = chatMessageList.atBottom;
                    var visibleIncomingCount = 0;
                    for (var i = 0; i < incomingMessages.length; i++) {
                        var message = incomingMessages[i];
                        if (message.chat_id !== chatId)
                            continue;

                        var found = false;
                        for (var j = 0; j < updated.length; j++) {
                            if (updated[j].id === message.id || (message.temp_id && updated[j].id === message.temp_id)) {
                                updated.splice(j, 1);
                                insertMessageSorted(updated, message);
                                found = true;
                                break;
                            }
                        }
                        if (!found) {
                            insertMessageSorted(updated, message);
                            if (!message.is_outgoing) {
                                if (wasAtBottom)
                                    visibleIncomingCount += 1;
                                else
                                    chatPage.unreadCount += 1;
                            }
                        }
                    }
                    messages = updated;
                    if (visibleIncomingCount > 0) {
                        messagesReadMetric.increment(visibleIncomingCount);
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
                setHandler('chat-list-update', function(updatedChats) {
                    for (var i = 0; i < updatedChats.length; i++) {
                        if (updatedChats[i].id === chatId) {
                            perfLog("chat-list-update triggering refresh reason=current-chat updated=" + updatedChats[i].id + " batchSize=" + updatedChats.length);
                            refreshPageState("chat-list-update:self");
                            return ;
                        }
                        for (var j = 0; j < messages.length; j++) {
                            var message = messages[j];
                            if (message.sender === updatedChats[i].id || message.reply_to_sender_id === updatedChats[i].id) {
                                perfLog("chat-list-update triggering refresh reason=sender-match updated=" + updatedChats[i].id + " messageId=" + (message.id || "") + " batchSize=" + updatedChats.length + " messageCount=" + messages.length);
                                refreshPageState("chat-list-update:sender-match");
                                return ;
                            }
                        }
                    }
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
