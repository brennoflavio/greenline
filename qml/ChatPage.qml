import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import Lomiri.Connectivity 1.0
import Lomiri.Content 1.3
import QtQuick 2.7
import UserMetrics 0.1
import "components"
import io.thp.pyotherside 1.4
import "lib/ChatHelpers.js" as ChatHelpers
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
    property string initialFirstUnreadMessageId: ""
    property int unreadCount: 0
    property string unreadDividerMessageId: initialFirstUnreadMessageId
    property bool suppressNextBottomReachedClear: initialFirstUnreadMessageId !== ""
    property string chatStatus: ""
    property string presenceStatus: ""
    property var activeTypers: ({
    })
    property string replyToMessageId: ""
    property string replyToSender: ""
    property string replyToText: ""
    property string replyToParticipant: ""
    property int editWindowSeconds: 20 * 60
    property bool pythonReady: false
    property bool refreshInProgress: false
    property bool refreshQueued: false
    property bool draftLoaded: false
    property bool draftTouchedBeforeLoad: false
    property bool draftSaveInFlight: false
    property string lastSavedDraftText: ""
    property string pendingDraftText: ""
    property var lastSavedDraftMentionSpans: []
    property var pendingDraftMentionSpans: []
    property var mentionCandidates: []

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
        if (!ChatHelpers.canReplyToMessage(message))
            return ;

        replyToMessageId = message.id;
        replyToSender = message.is_outgoing ? i18n.tr("You") : (message.sender_name || chatName || message.sender || "");
        replyToText = ChatHelpers.messagePreview(message, i18n, {
            "link_preview": "🔗 Link"
        });
        replyToParticipant = message.is_outgoing ? "" : (message.sender || "");
        chatComposer.focusInput();
    }

    function canEditMessage(message) {
        var timestampUnix = message && message.timestamp_unix ? message.timestamp_unix : 0;
        return !!message && !!message.is_outgoing && !!message.id && message.id.indexOf("pending-") !== 0 && message.id.indexOf("failed-") !== 0 && (message.type || "") === "text" && ChatHelpers.messageMentionedJids(message).length === 0 && ChatHelpers.messageMentionSpans(message).length === 0 && timestampUnix > 0 && Math.floor(Date.now() / 1000) - timestampUnix <= editWindowSeconds;
    }

    function canDeleteMessage(message) {
        var sendStatus = message && message.send_status ? message.send_status : "";
        return !!message && !!message.is_outgoing && !!message.id && message.id.indexOf("pending-") !== 0 && message.id.indexOf("failed-") !== 0 && sendStatus !== "pending" && sendStatus !== "failed" && (message.type || "") !== "deleted";
    }

    function startEdit(message) {
        if (!canEditMessage(message))
            return ;

        PopupUtils.open(editMessageDialog, chatPage, {
            "messageId": message.id,
            "initialText": message.text || ""
        });
    }

    function submitEditedMessage(dialog, messageId, text) {
        python.call('main.edit_text_message', [chatId, messageId, text], function(result) {
            if (result && result.success) {
                PopupUtils.close(dialog);
                toast.show(i18n.tr("Message updated"));
                return ;
            }
            if (dialog)
                dialog.saving = false;

            toast.show(result && result.message ? result.message : i18n.tr("Failed to edit message"));
        });
    }

    function deleteSelectedMessage(message) {
        if (!canDeleteMessage(message))
            return ;

        python.call('main.delete_message', [chatId, message.id], function(result) {
            if (result && result.success) {
                toast.show(i18n.tr("Message deleted"));
                return ;
            }
            toast.show(result && result.message ? result.message : i18n.tr("Failed to delete message"));
        });
    }

    function scrollToMessage(messageId) {
        chatMessageList.scrollToMessage(messageId);
    }

    function markChatAsRead(readCount, preserveDivider) {
        var unreadToClear = Math.max(0, readCount || 0);
        unreadCount = 0;
        if (!preserveDivider)
            unreadDividerMessageId = "";

        if (unreadToClear > 0)
            messagesReadMetric.increment(unreadToClear);

        python.call('main.mark_messages_as_read', [chatId], function() {
        });
    }

    function triggerDownload(messageId, mediaType) {
        if (!Connectivity.online) {
            toast.show(i18n.tr("No internet connection. Connect and try again."));
            return ;
        }
        var d = Object.assign({
        }, downloadingIds);
        d[messageId] = true;
        downloadingIds = d;
        python.call('main.download_media', [chatId, messageId, mediaType], function(result) {
            var d2 = Object.assign({
            }, downloadingIds);
            delete d2[messageId];
            downloadingIds = d2;
            if (!result || !result.success)
                toast.show(result && result.message ? result.message : i18n.tr("Failed to download media"));

        });
    }

    function openMessageReactions(message) {
        if (!chatMessageList.canReactMessage(message))
            return ;

        pageStack.push(Qt.resolvedUrl("MessageReactionsPage.qml"), {
            "chatId": chatId,
            "chatName": chatName,
            "messageId": message.id
        });
    }

    function loadInitialMessages() {
        python.call('main.get_messages', [chatId, "", messagePageSize], function(result) {
            if (result && result.success) {
                nextMessagesCursor = result.next_cursor || "";
                hasOlderMessages = !!result.has_more;
                messages = result.messages;
                var unreadOnOpen = initialUnreadCount;
                if (unreadOnOpen > 0) {
                    initialUnreadCount = 0;
                    markChatAsRead(unreadOnOpen, true);
                }
            }
        });
    }

    function loadMentionCandidates() {
        if (!isGroup) {
            mentionCandidates = [];
            return ;
        }
        python.call('main.get_group_mention_candidates', [chatId], function(result) {
            if (result && result.success)
                mentionCandidates = result.candidates || [];
            else
                mentionCandidates = [];
        });
    }

    function loadDraft() {
        python.call('main.get_chat_draft', [chatId], function(result) {
            var draftText = result && result.success ? (result.text || "") : "";
            var draftMentionSpans = result && result.success ? ChatHelpers.cloneMentionSpans(result.mention_spans || []) : [];
            if (!draftTouchedBeforeLoad && (chatComposer.text || "") === "") {
                lastSavedDraftText = draftText;
                pendingDraftText = draftText;
                lastSavedDraftMentionSpans = draftMentionSpans;
                pendingDraftMentionSpans = ChatHelpers.cloneMentionSpans(draftMentionSpans);
                draftLoaded = true;
                chatComposer.setTextAndMentions(draftText, draftMentionSpans);
                return ;
            }
            if (pendingDraftText === draftText && ChatHelpers.mentionSpansEqual(pendingDraftMentionSpans, draftMentionSpans) && !draftSaveInFlight) {
                lastSavedDraftText = draftText;
                lastSavedDraftMentionSpans = ChatHelpers.cloneMentionSpans(draftMentionSpans);
            }
            draftLoaded = true;
            if (pendingDraftText !== lastSavedDraftText || !ChatHelpers.mentionSpansEqual(pendingDraftMentionSpans, lastSavedDraftMentionSpans))
                saveDraft(pendingDraftText, pendingDraftMentionSpans);

        });
    }

    function saveDraft(text, mentionSpans) {
        if (!pythonReady)
            return ;

        pendingDraftText = text;
        pendingDraftMentionSpans = ChatHelpers.cloneMentionSpans(mentionSpans);
        if (!draftLoaded && !draftTouchedBeforeLoad)
            return ;

        if (draftSaveInFlight)
            return ;

        if (pendingDraftText === lastSavedDraftText && ChatHelpers.mentionSpansEqual(pendingDraftMentionSpans, lastSavedDraftMentionSpans))
            return ;

        var textToSave = pendingDraftText;
        var mentionSpansToSave = ChatHelpers.cloneMentionSpans(pendingDraftMentionSpans);
        draftSaveInFlight = true;
        python.call('main.set_chat_draft', [chatId, textToSave, mentionSpansToSave], function(result) {
            draftSaveInFlight = false;
            if (result && result.success) {
                lastSavedDraftText = textToSave;
                lastSavedDraftMentionSpans = ChatHelpers.cloneMentionSpans(mentionSpansToSave);
            }
            if (pendingDraftText !== textToSave || !ChatHelpers.mentionSpansEqual(pendingDraftMentionSpans, mentionSpansToSave))
                saveDraft(pendingDraftText, pendingDraftMentionSpans);

        });
    }

    function flushDraft() {
        draftSaveTimer.stop();
        saveDraft(chatComposer.text || "", chatComposer.mentionSpans || []);
    }

    function refreshPageState(reason) {
        function finishRefresh() {
            pendingCallbacks -= 1;
            if (pendingCallbacks === 0) {
                var queued = refreshQueued;
                refreshInProgress = false;
                if (queued)
                    refreshPageState("queued-after-" + reason);

            }
        }

        reason = reason || "unknown";
        if (!pythonReady)
            return ;

        if (refreshInProgress) {
            refreshQueued = true;
            return ;
        }
        refreshInProgress = true;
        refreshQueued = false;
        var pendingCallbacks = 2;
        var wasAtBottom = chatMessageList.atBottom;
        python.call('main.get_chat_info', [chatId], function(result) {
            if (result && result.success) {
                chatName = result.name || chatName;
                chatPhoto = result.photo || "";
                isGroup = !!result.is_group;
                if (isGroup && mentionCandidates.length === 0)
                    loadMentionCandidates();
                else if (!isGroup)
                    mentionCandidates = [];
                if (wasAtBottom) {
                    if (result.unread_count > 0)
                        markChatAsRead(result.unread_count, false);

                } else {
                    unreadCount = result.unread_count || 0;
                    if (result.first_unread_message_id && unreadDividerMessageId === "")
                        unreadDividerMessageId = result.first_unread_message_id;

                }
            }
            finishRefresh();
        });
        python.call('main.get_messages', [chatId, "", messagePageSize], function(result) {
            if (result && result.success) {
                nextMessagesCursor = result.next_cursor || "";
                hasOlderMessages = !!result.has_more;
                messages = ChatHelpers.mergeRefreshedMessages(messages, result.messages || []);
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

    function sendAudioMessage(filePath, durationSeconds) {
        var tempId = "pending-" + Date.now();
        var now = new Date();
        var timestampUnix = Math.floor(now.getTime() / 1000);
        var hours = now.getHours().toString();
        if (hours.length < 2)
            hours = "0" + hours;

        var minutes = now.getMinutes().toString();
        if (minutes.length < 2)
            minutes = "0" + minutes;

        var totalSeconds = Math.max(0, Math.floor(durationSeconds || 0));
        var replyContext = consumeReplyContext();
        var pendingMsg = {
            "id": tempId,
            "chat_id": chatId,
            "type": "audio",
            "is_outgoing": true,
            "text": "",
            "timestamp": hours + ":" + minutes,
            "timestamp_unix": timestampUnix,
            "read_receipt": "",
            "send_status": "pending",
            "temp_id": tempId,
            "media_path": "file://" + filePath,
            "duration": Math.floor(totalSeconds / 60) + ":" + ((totalSeconds % 60) < 10 ? "0" : "") + (totalSeconds % 60),
            "reply_to_id": replyContext ? replyContext.id : "",
            "reply_to_sender": replyContext ? replyContext.sender : "",
            "reply_to_text": replyContext ? replyContext.text : ""
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesSendAttemptsMetric.increment(1);
        python.call('main.send_audio_message', [chatId, filePath, totalSeconds, tempId, replyContext], function(result) {
            if (result && !result.success)
                toast.show(result.message || i18n.tr("Failed to send audio"));

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

    function sendDocumentMessage(filePath) {
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
            "type": "document",
            "is_outgoing": true,
            "text": "",
            "caption": "",
            "timestamp": hours + ":" + minutes,
            "timestamp_unix": timestampUnix,
            "read_receipt": "",
            "send_status": "pending",
            "temp_id": tempId,
            "file_name": ChatHelpers.fileNameFromPath(filePath, i18n.tr("Document")),
            "media_path": "file://" + filePath,
            "reply_to_id": replyContext ? replyContext.id : "",
            "reply_to_sender": replyContext ? replyContext.sender : "",
            "reply_to_text": replyContext ? replyContext.text : ""
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesSendAttemptsMetric.increment(1);
        python.call('main.send_document_message', [chatId, filePath, "", tempId, replyContext], function(result) {
            if (result && !result.success)
                toast.show(result.message || i18n.tr("Failed to send document"));

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
            "file_name": ChatHelpers.contactNameFromPath(filePath, i18n),
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

    function sendLocationMessage(latitude, longitude) {
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
        var coordinates = latitude + ", " + longitude;
        var pendingMsg = {
            "id": tempId,
            "chat_id": chatId,
            "type": "location",
            "is_outgoing": true,
            "text": coordinates,
            "caption": "",
            "link_url": "geo:" + latitude + "," + longitude,
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
        python.call('main.send_location_message', [chatId, latitude, longitude, tempId, replyContext], function(result) {
            if (result && !result.success)
                toast.show(result.message || i18n.tr("Failed to send location"));

        });
    }

    function sendMessage() {
        Qt.inputMethod.commit();
        if (chatComposer.text.length > 0) {
            var text = chatComposer.text;
            var mentionSpans = ChatHelpers.cloneMentionSpans(chatComposer.mentionSpans || []);
            var tempId = "pending-" + Date.now();
            var now = new Date();
            var timestampUnix = Math.floor(now.getTime() / 1000);
            var hours = now.getHours().toString();
            if (hours.length < 2)
                hours = "0" + hours;

            var minutes = now.getMinutes().toString();
            if (minutes.length < 2)
                minutes = "0" + minutes;

            var mentionedJids = [];
            for (var i = 0; i < mentionSpans.length; i++) mentionedJids.push(mentionSpans[i].jid)
            var replyContext = consumeReplyContext();
            var pendingMsg = {
                "id": tempId,
                "chat_id": chatId,
                "type": "text",
                "is_outgoing": true,
                "text": text,
                "mentioned_jids": mentionedJids,
                "mention_spans": mentionSpans,
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
            chatComposer.setTextAndMentions("", []);
            draftSaveTimer.stop();
            saveDraft("", []);
            python.call('main.send_text_message', [chatId, text, tempId, replyContext, mentionSpans], function() {
            });
        }
    }

    onMessagesChanged: {
        if (chatMessageList)
            chatMessageList.messages = messages;

    }
    Component.onDestruction: flushDraft()

    Timer {
        id: draftSaveTimer

        interval: 500
        repeat: false
        onTriggered: chatPage.saveDraft(chatComposer.text || "", chatComposer.mentionSpans || [])
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

        hasOlderMessages: chatPage.hasOlderMessages
        loadingOlderMessages: chatPage.loadingOlderMessages
        downloadingIds: chatPage.downloadingIds
        isGroup: chatPage.isGroup
        unreadCount: chatPage.unreadCount
        unreadDividerMessageId: chatPage.unreadDividerMessageId
        editWindowSeconds: chatPage.editWindowSeconds
        onBottomReached: {
            if (chatPage.suppressNextBottomReachedClear && chatPage.unreadCount === 0) {
                chatPage.suppressNextBottomReachedClear = false;
                return ;
            }
            chatPage.suppressNextBottomReachedClear = false;
            if (chatPage.unreadCount > 0) {
                var unreadWhileAway = chatPage.unreadCount;
                chatPage.markChatAsRead(unreadWhileAway, false);
            } else if (chatPage.unreadDividerMessageId !== "") {
                chatPage.unreadDividerMessageId = "";
            }
        }
        onOlderMessagesRequested: chatPage.loadOlderMessages()
        onMessageNotLoaded: toast.show(i18n.tr("Scroll up to load older messages first"))
        onReplyRequested: chatPage.startReply(message)
        onEditRequested: chatPage.startEdit(message)
        onDeleteRequested: chatPage.deleteSelectedMessage(message)
        onReactionsRequested: chatPage.openMessageReactions(message)
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
        mentionCandidates: chatPage.mentionCandidates
        onTextChanged: {
            chatPage.pendingDraftText = chatComposer.text || "";
            if (!chatPage.draftLoaded)
                chatPage.draftTouchedBeforeLoad = true;

            draftSaveTimer.restart();
        }
        onMentionSpansChanged: {
            chatPage.pendingDraftMentionSpans = ChatHelpers.cloneMentionSpans(chatComposer.mentionSpans || []);
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
                if (initialFirstUnreadMessageId !== "" && unreadDividerMessageId === "")
                    unreadDividerMessageId = initialFirstUnreadMessageId;

                suppressNextBottomReachedClear = unreadDividerMessageId !== "";
                if (initialUnreadCount > 0 && initialFirstUnreadMessageId === "") {
                    python.call('main.get_chat_info', [chatId], function(result) {
                        if (result && result.success && result.first_unread_message_id) {
                            initialFirstUnreadMessageId = result.first_unread_message_id;
                            unreadDividerMessageId = result.first_unread_message_id;
                        }
                        loadInitialMessages();
                    });
                } else {
                    loadInitialMessages();
                }
                loadDraft();
                if (isGroup)
                    loadMentionCandidates();
                else
                    python.call('main.subscribe_presence', [chatId], function() {
                });
                setHandler('message-upsert', function(incomingMessages) {
                    var updated = messages.slice();
                    var wasAtBottom = chatMessageList.atBottom;
                    var visibleIncomingCount = 0;
                    var shouldAnchorNewUnread = !wasAtBottom && chatPage.unreadCount === 0 && chatPage.unreadDividerMessageId === "";
                    var oldestNewUnreadMessage = null;
                    for (var i = 0; i < incomingMessages.length; i++) {
                        var message = incomingMessages[i];
                        if (message.chat_id !== chatId)
                            continue;

                        if (message.id === replyToMessageId && message.type === "deleted")
                            replyToText = ChatHelpers.messagePreview(message, i18n, {
                            "link_preview": "🔗 Link"
                        });

                        var found = false;
                        for (var j = 0; j < updated.length; j++) {
                            if (updated[j].id === message.id || (message.temp_id && updated[j].id === message.temp_id)) {
                                updated.splice(j, 1);
                                ChatHelpers.insertMessageSorted(updated, message);
                                found = true;
                                break;
                            }
                        }
                        if (!found) {
                            ChatHelpers.insertMessageSorted(updated, message);
                            if (!message.is_outgoing) {
                                if (wasAtBottom) {
                                    visibleIncomingCount += 1;
                                } else {
                                    if (shouldAnchorNewUnread && (oldestNewUnreadMessage === null || ChatHelpers.messageComesBefore(message, oldestNewUnreadMessage)))
                                        oldestNewUnreadMessage = message;

                                    chatPage.unreadCount += 1;
                                }
                            }
                        }
                    }
                    messages = updated;
                    if (oldestNewUnreadMessage !== null)
                        chatPage.unreadDividerMessageId = oldestNewUnreadMessage.id;

                    if (visibleIncomingCount > 0)
                        chatPage.markChatAsRead(visibleIncomingCount, false);

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
                            refreshPageState("chat-list-update:self");
                            return ;
                        }
                        for (var j = 0; j < messages.length; j++) {
                            var message = messages[j];
                            if (message.sender === updatedChats[i].id || message.reply_to_sender_id === updatedChats[i].id) {
                                refreshPageState("chat-list-update:sender-match");
                                return ;
                            }
                        }
                    }
                });
            });
        }
        onError: {
            if (Object.keys(downloadingIds).length > 0) {
                downloadingIds = ({
                });
                toast.show(i18n.tr("Failed to download media"));
            }
        }
    }

    Component {
        id: editMessageDialog

        EditMessageDialog {
            id: dialog

            onSaveRequested: chatPage.submitEditedMessage(dialog, messageId, text)
        }

    }

    Component {
        id: attachmentDialog

        ChatAttachmentDialog {
            onPhotoRequested: pageStack.push(mediaPickerPage)
            onVideoRequested: pageStack.push(videoPickerPage)
            onAudioRequested: PopupUtils.open(voiceMessageRecorderDialog, chatPage)
            onDocumentRequested: pageStack.push(documentPickerPage)
            onStickerRequested: pageStack.push(stickerPickerComponent)
            onContactRequested: pageStack.push(contactPickerPage)
            onLocationRequested: PopupUtils.open(locationFetchDialog, chatPage)
        }

    }

    Component {
        id: voiceMessageRecorderDialog

        VoiceMessageRecorderDialog {
            onRecordingAccepted: sendAudioMessage(filePath, durationSeconds)
        }

    }

    Component {
        id: locationFetchDialog

        LocationFetchDialog {
            onLocationSelected: sendLocationMessage(latitude, longitude)
            onFetchFailed: toast.show(message)
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
        id: documentPickerPage

        ChatAttachmentPickerPage {
            pickerTitle: i18n.tr("Send Document")
            pickerContentType: ContentType.Documents
            onFileSelected: sendDocumentMessage(filePath)
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

    header: ChatPageHeader {
        id: chatHeader

        chatName: chatPage.chatName
        chatPhoto: chatPage.chatPhoto
        chatStatus: chatPage.chatStatus
        onBackRequested: pageStack.pop()
        onProfileRequested: {
            pageStack.push(Qt.resolvedUrl("ProfilePage.qml"), {
                "chatId": chatId,
                "chatName": chatName,
                "chatPhoto": chatPhoto
            });
        }
    }

}
