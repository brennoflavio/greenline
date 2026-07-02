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
    property int messagePageSize: 20
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
    property var senderMetadataByJid: ({
    })
    property string replyToMessageId: ""
    property string replyToSender: ""
    property string replyToText: ""
    property string replyToParticipant: ""
    property int editWindowSeconds: 20 * 60
    property bool pythonReady: false
    property bool metadataRefreshInProgress: false
    property bool metadataRefreshQueued: false
    property bool messageRecoveryInProgress: false
    property bool messageRecoveryQueued: false
    property bool draftLoaded: false
    property bool draftTouchedBeforeLoad: false
    property bool draftSaveInFlight: false
    property string lastSavedDraftText: ""
    property string pendingDraftText: ""
    property var lastSavedDraftMentionSpans: []
    property var pendingDraftMentionSpans: []
    property var mentionCandidates: []
    property bool deferredOpenTasksScheduled: false
    property int deferredOpenTasksDelayMs: 300

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

    function senderMetadataForJid(jid) {
        if (!jid || !senderMetadataByJid.hasOwnProperty(jid))
            return null;

        return senderMetadataByJid[jid];
    }

    function applySenderMetadataEntries(entries, options) {
        var nextEntries = entries || [];
        if (nextEntries.length === 0)
            return false;

        var updateOptions = options || {
        };
        var fillMissingOnly = !!updateOptions.fillMissingOnly;
        var allowEmptyName = !!updateOptions.allowEmptyName;
        var allowEmptyPhoto = !!updateOptions.allowEmptyPhoto;
        var updatedMetadataByJid = Object.assign({
        }, senderMetadataByJid);
        var changed = false;
        for (var i = 0; i < nextEntries.length; i++) {
            var entry = nextEntries[i];
            if (!entry || !entry.jid)
                continue;

            var currentMetadata = updatedMetadataByJid[entry.jid] || {
            };
            var nextMetadata = Object.assign({
            }, currentMetadata);
            if (typeof entry.name !== "undefined" && (entry.name !== "" || allowEmptyName) && (!fillMissingOnly || !nextMetadata.name) && nextMetadata.name !== entry.name) {
                nextMetadata.name = entry.name;
                changed = true;
            }
            if (typeof entry.photo !== "undefined" && (entry.photo !== "" || allowEmptyPhoto) && (!fillMissingOnly || !nextMetadata.photo) && nextMetadata.photo !== entry.photo) {
                nextMetadata.photo = entry.photo;
                changed = true;
            }
            updatedMetadataByJid[entry.jid] = nextMetadata;
        }
        if (!changed)
            return false;

        senderMetadataByJid = updatedMetadataByJid;
        return true;
    }

    function seedSenderMetadataFromMessage(message) {
        if (!message)
            return false;

        var entries = [];
        if (message.sender)
            entries.push({
            "jid": message.sender,
            "name": message.sender_name || "",
            "photo": message.sender_photo || ""
        });

        if (!message.reply_to_from_me && message.reply_to_sender_id)
            entries.push({
            "jid": message.reply_to_sender_id,
            "name": message.reply_to_sender || ""
        });

        return applySenderMetadataEntries(entries, {
            "fillMissingOnly": true
        });
    }

    function seedSenderMetadataFromMessages(messageList) {
        var nextMessages = messageList || [];
        var entries = [];
        for (var i = 0; i < nextMessages.length; i++) {
            var message = nextMessages[i];
            if (!message)
                continue;

            if (message.sender)
                entries.push({
                "jid": message.sender,
                "name": message.sender_name || "",
                "photo": message.sender_photo || ""
            });

            if (!message.reply_to_from_me && message.reply_to_sender_id)
                entries.push({
                "jid": message.reply_to_sender_id,
                "name": message.reply_to_sender || ""
            });

        }
        return applySenderMetadataEntries(entries, {
            "fillMissingOnly": true
        });
    }

    function applySenderMetadataChatUpdates(updatedChats) {
        var nextChats = updatedChats || [];
        var entries = [];
        for (var i = 0; i < nextChats.length; i++) {
            var chat = nextChats[i];
            if (!chat || !chat.id)
                continue;

            entries.push({
                "jid": chat.id,
                "name": chat.name || "",
                "photo": typeof chat.photo !== "undefined" ? (chat.photo || "") : undefined
            });
        }
        return applySenderMetadataEntries(entries, {
            "allowEmptyPhoto": true
        });
    }

    function applySenderMetadataPhotoUpdates(photoList) {
        var nextPhotos = photoList || [];
        var entries = [];
        for (var i = 0; i < nextPhotos.length; i++) {
            var entry = nextPhotos[i];
            if (!entry || !entry.jid)
                continue;

            entries.push({
                "jid": entry.jid,
                "photo": entry.photo || ""
            });
        }
        return applySenderMetadataEntries(entries, {
            "allowEmptyPhoto": true
        });
    }

    function resolveSenderDisplayName(jid, fallbackName) {
        var metadata = senderMetadataForJid(jid);
        if (metadata && metadata.name)
            return metadata.name;

        if (fallbackName)
            return fallbackName;

        if (jid === chatId && chatName)
            return chatName;

        return jid || "";
    }

    function resolveMessageSenderDisplayName(message) {
        if (!message)
            return "";

        if (message.is_outgoing)
            return i18n.tr("You");

        return resolveSenderDisplayName(message.sender || chatId, message.sender_name || "");
    }

    function startReply(message) {
        if (!ChatHelpers.canReplyToMessage(message))
            return ;

        replyToMessageId = message.id;
        replyToSender = resolveMessageSenderDisplayName(message);
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
                resetChatMessages(result.messages || []);
                scheduleDeferredOpenTasks();
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

    function scheduleDeferredOpenTasks() {
        if (deferredOpenTasksScheduled)
            return ;

        deferredOpenTasksScheduled = true;
        deferredOpenTasksTimer.restart();
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

    function hasLoadedMessage(messageId) {
        if (!messageId)
            return false;

        for (var i = 0; i < messages.length; i++) {
            if (messages[i].id === messageId || messages[i].temp_id === messageId)
                return true;

        }
        return false;
    }

    function findMessageIndexByIdOrTempId(messageList, messageId, tempId) {
        for (var i = 0; i < messageList.length; i++) {
            var currentMessage = messageList[i];
            var currentId = currentMessage.id || "";
            var currentTempId = currentMessage.temp_id || "";
            if (messageId !== "" && (currentId === messageId || currentTempId === messageId))
                return i;

            if (tempId !== "" && (currentId === tempId || currentTempId === tempId))
                return i;

        }
        return -1;
    }

    function setChatMessages(nextMessages) {
        messages = nextMessages || [];
    }

    function resetChatMessages(nextMessages) {
        setChatMessages(nextMessages);
        seedSenderMetadataFromMessages(messages);
        if (chatMessageList)
            chatMessageList.resetMessages(messages);

    }

    function replaceMessageSorted(messageList, message) {
        var replaceIndex = findMessageIndexByIdOrTempId(messageList, message && message.id ? message.id : "", message && message.temp_id ? message.temp_id : "");
        if (replaceIndex !== -1)
            messageList.splice(replaceIndex, 1);

        ChatHelpers.insertMessageSorted(messageList, message);
    }

    function replaceChatMessageByIdOrTempId(message) {
        if (!message)
            return ;

        var updatedMessages = messages.slice();
        replaceMessageSorted(updatedMessages, message);
        setChatMessages(updatedMessages);
        seedSenderMetadataFromMessage(message);
        if (chatMessageList)
            chatMessageList.replaceMessageByIdOrTempId(message);

    }

    function appendPendingChatMessage(message) {
        if (!message)
            return ;

        var updatedMessages = messages.slice();
        ChatHelpers.insertMessageSorted(updatedMessages, message);
        setChatMessages(updatedMessages);
        if (chatMessageList)
            chatMessageList.appendPendingMessage(message);

    }

    function upsertChatMessages(incomingMessages) {
        var nextMessages = incomingMessages || [];
        var updatedMessages = messages.slice();
        for (var i = 0; i < nextMessages.length; i++) {
            if (nextMessages[i])
                replaceMessageSorted(updatedMessages, nextMessages[i]);

        }
        setChatMessages(updatedMessages);
        seedSenderMetadataFromMessages(nextMessages);
        if (chatMessageList)
            chatMessageList.upsertMessages(nextMessages);

    }

    function appendOlderChatMessages(olderMessages, anchorMessageId) {
        var nextOlderMessages = olderMessages || [];
        setChatMessages(nextOlderMessages.concat(messages));
        seedSenderMetadataFromMessages(nextOlderMessages);
        if (chatMessageList)
            chatMessageList.appendOlderMessages(nextOlderMessages, anchorMessageId || "");

    }

    function patchChatMessages(patches) {
        var nextPatches = patches || [];
        if (nextPatches.length === 0)
            return false;

        var updatedMessages = messages.slice();
        var appliedPatches = [];
        for (var i = 0; i < nextPatches.length; i++) {
            var nextPatch = nextPatches[i];
            var patchIndex = findMessageIndexByIdOrTempId(updatedMessages, nextPatch.messageId || "", nextPatch.tempId || "");
            if (patchIndex === -1)
                continue;

            var currentMessage = updatedMessages[patchIndex];
            var patch = nextPatch.patch || {
            };
            var changed = false;
            for (var field in patch) {
                if (!ChatHelpers.fieldValuesEqual(currentMessage[field], patch[field])) {
                    changed = true;
                    break;
                }
            }
            if (!changed)
                continue;

            updatedMessages[patchIndex] = Object.assign({
            }, currentMessage, patch);
            appliedPatches.push({
                "messageId": nextPatch.messageId || "",
                "tempId": nextPatch.tempId || "",
                "patch": patch
            });
        }
        if (appliedPatches.length === 0)
            return false;

        setChatMessages(updatedMessages);
        if (chatMessageList) {
            for (var j = 0; j < appliedPatches.length; j++) chatMessageList.patchMessageByIdOrTempId(appliedPatches[j].messageId, appliedPatches[j].tempId, appliedPatches[j].patch)
        }
        return true;
    }

    function patchChatMessageByIdOrTempId(messageId, tempId, patch) {
        return patchChatMessages([{
            "messageId": messageId || "",
            "tempId": tempId || "",
            "patch": patch || {
            }
        }]);
    }

    function applyChatMetadata(chat, wasAtBottom, allowReadMarking) {
        if (!chat)
            return ;

        if (typeof allowReadMarking === "undefined")
            allowReadMarking = true;

        chatName = chat.name || chatName;
        if (typeof chat.photo !== "undefined")
            chatPhoto = chat.photo || "";

        isGroup = !!chat.is_group;
        if (isGroup && mentionCandidates.length === 0)
            loadMentionCandidates();
        else if (!isGroup)
            mentionCandidates = [];
        if (wasAtBottom) {
            if (allowReadMarking && (chat.unread_count || 0) > 0)
                markChatAsRead(chat.unread_count, false);

            return ;
        }
        unreadCount = chat.unread_count || 0;
        if (chat.first_unread_message_id && unreadDividerMessageId === "")
            unreadDividerMessageId = chat.first_unread_message_id;

    }

    function refreshChatMetadata(reason, allowReadMarking, onSuccess) {
        function finishRefresh() {
            var queued = metadataRefreshQueued;
            metadataRefreshInProgress = false;
            metadataRefreshQueued = false;
            if (queued)
                refreshChatMetadata("queued-after-" + reason, allowReadMarking, onSuccess);

        }

        reason = reason || "unknown";
        if (!pythonReady)
            return ;

        if (typeof allowReadMarking === "function") {
            onSuccess = allowReadMarking;
            allowReadMarking = true;
        }
        if (typeof allowReadMarking === "undefined")
            allowReadMarking = true;

        if (metadataRefreshInProgress) {
            metadataRefreshQueued = true;
            return ;
        }
        metadataRefreshInProgress = true;
        python.call('main.get_chat_info', [chatId], function(result) {
            if (result && result.success) {
                applyChatMetadata(result, chatMessageList.atBottom, allowReadMarking);
                if (onSuccess)
                    onSuccess(result, chatMessageList.atBottom);

            }
            finishRefresh();
        });
    }

    function recoverMessages(reason, onSuccess) {
        function finishRecovery() {
            var queued = messageRecoveryQueued;
            messageRecoveryInProgress = false;
            messageRecoveryQueued = false;
            if (queued)
                recoverMessages("queued-after-" + reason, onSuccess);

        }

        reason = reason || "unknown";
        if (!pythonReady)
            return ;

        if (messageRecoveryInProgress) {
            messageRecoveryQueued = true;
            return ;
        }
        messageRecoveryInProgress = true;
        var wasAtBottom = chatMessageList.atBottom;
        python.call('main.get_messages', [chatId, "", messagePageSize], function(result) {
            if (result && result.success) {
                nextMessagesCursor = result.next_cursor || "";
                hasOlderMessages = !!result.has_more;
                resetChatMessages(ChatHelpers.mergeRefreshedMessages(messages, result.messages || []));
                if (wasAtBottom)
                    chatMessageList.scrollToBottom();

                if (onSuccess)
                    onSuccess(result);

            }
            finishRecovery();
        });
    }

    function refreshAppActiveState() {
        refreshChatMetadata("app-active", false, function(result, wasAtBottom) {
            if (!result || !result.success)
                return ;

            if (messages.length === 0) {
                recoverMessages("app-active:missing-messages", function(recoveryResult) {
                    if (recoveryResult && recoveryResult.success && wasAtBottom && (result.unread_count || 0) > 0)
                        refreshChatMetadata("app-active:post-recovery");

                });
                return ;
            }
            if (!wasAtBottom || (result.unread_count || 0) <= 0)
                return ;

            if (result.first_unread_message_id && hasLoadedMessage(result.first_unread_message_id)) {
                markChatAsRead(result.unread_count, false);
                return ;
            }
            recoverMessages("app-active:unread-recovery", function(recoveryResult) {
                if (recoveryResult && recoveryResult.success && chatMessageList.atBottom)
                    refreshChatMetadata("app-active:post-recovery");

            });
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

            appendOlderChatMessages(result.messages || [], anchorMessageId);
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
        appendPendingChatMessage(pendingMsg);
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
        appendPendingChatMessage(pendingMsg);
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
        appendPendingChatMessage(pendingMsg);
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
        appendPendingChatMessage(pendingMsg);
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
        appendPendingChatMessage(pendingMsg);
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
        appendPendingChatMessage(pendingMsg);
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
        appendPendingChatMessage(pendingMsg);
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
            appendPendingChatMessage(pendingMsg);
            messagesSendAttemptsMetric.increment(1);
            chatComposer.setTextAndMentions("", []);
            draftSaveTimer.stop();
            saveDraft("", []);
            python.call('main.send_text_message', [chatId, text, tempId, replyContext, mentionSpans], function() {
            });
        }
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
        senderMetadataByJid: chatPage.senderMetadataByJid
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
            if (!chatPage.draftLoaded && chatPage.pendingDraftText !== "")
                chatPage.draftTouchedBeforeLoad = true;

            draftSaveTimer.restart();
        }
        onMentionSpansChanged: {
            chatPage.pendingDraftMentionSpans = ChatHelpers.cloneMentionSpans(chatComposer.mentionSpans || []);
            if (!chatPage.draftLoaded && chatPage.pendingDraftMentionSpans.length > 0)
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
                refreshAppActiveState();
            else
                flushDraft();
        }
    }

    Timer {
        id: deferredOpenTasksTimer

        interval: deferredOpenTasksDelayMs
        repeat: false
        onTriggered: {
            loadDraft();
            if (!isGroup)
                python.call('main.subscribe_presence', [chatId], function() {
            });

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
                if (isGroup)
                    loadMentionCandidates();

                setHandler('message-upsert', function(incomingMessages) {
                    var updated = messages.slice();
                    var messagesToUpsert = [];
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

                        var found = findMessageIndexByIdOrTempId(updated, message.id || "", message.temp_id || "") !== -1;
                        replaceMessageSorted(updated, message);
                        messagesToUpsert.push(message);
                        if (!found && !message.is_outgoing) {
                            if (wasAtBottom) {
                                visibleIncomingCount += 1;
                            } else {
                                if (shouldAnchorNewUnread && (oldestNewUnreadMessage === null || ChatHelpers.messageComesBefore(message, oldestNewUnreadMessage)))
                                    oldestNewUnreadMessage = message;

                                chatPage.unreadCount += 1;
                            }
                        }
                    }
                    if (messagesToUpsert.length > 0)
                        upsertChatMessages(messagesToUpsert);

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
                    applySenderMetadataPhotoUpdates(photoList);
                });
                setHandler('chat-list-update', function(updatedChats) {
                    applySenderMetadataChatUpdates(updatedChats);
                    for (var i = 0; i < updatedChats.length; i++) {
                        if (updatedChats[i].id === chatId) {
                            applyChatMetadata(updatedChats[i], chatMessageList.atBottom, false);
                            break;
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
