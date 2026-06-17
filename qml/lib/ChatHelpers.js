.pragma library

function tr(i18n, text) {
    return i18n && i18n.tr ? i18n.tr(text) : text;
}

function cloneMentionSpans(spans) {
    return JSON.parse(JSON.stringify(spans || []));
}

function mentionSpansEqual(left, right) {
    return JSON.stringify(left || []) === JSON.stringify(right || []);
}

function messageMentionSpans(message) {
    return cloneMentionSpans(message && message.mention_spans ? message.mention_spans : []);
}

function messageMentionedJids(message) {
    return message && message.mentioned_jids ? message.mentioned_jids : [];
}

function locationPreview(title, detail) {
    var previewTitle = title ? title.toString().trim() : "";
    if (previewTitle !== "")
        return "📍 " + previewTitle;

    var previewDetail = detail ? detail.toString().trim() : "";
    if (previewDetail !== "")
        return "📍 " + previewDetail;

    return "📍 Location";
}

function messagePreview(message, i18n, extraPreviews) {
    if (!message)
        return "";

    if (message.type === "deleted")
        return tr(i18n, "Deleted message");

    if (message.type === "view_once")
        return tr(i18n, "View-once message. Open WhatsApp on your primary device to view it.");

    if (message.type === "location")
        return locationPreview(message.text, message.caption);

    if (message.text)
        return message.text;

    if (message.caption)
        return message.caption;

    if (message.type === "contact")
        return "👤 " + (message.file_name || tr(i18n, "Contact"));

    var previews = {
        "image": "📷 Photo",
        "video": "🎥 Video",
        "audio": "🎵 Audio",
        "document": "📄 Document",
        "sticker": "🏷️ Sticker",
        "location": "📍 Location"
    };
    if (extraPreviews) {
        for (var type in extraPreviews)
            previews[type] = extraPreviews[type];
    }
    return previews[message.type] || message.type || "";
}

function chatPreview(chat, i18n) {
    if (chat.has_draft)
        return tr(i18n, "Draft: ") + (chat.draft || "");

    if ((chat.last_message_type || "") === "deleted")
        return tr(i18n, "Deleted message");

    if ((chat.last_message_type || "") === "view_once")
        return tr(i18n, "View-once message. Open WhatsApp on your primary device to view it.");

    return chat.last_message || "";
}

function fileNameFromPath(filePath, fallbackName) {
    var cleanPath = filePath.toString().replace("file://", "");
    var parts = cleanPath.split("/");
    var name = parts.length > 0 ? parts[parts.length - 1] : "";
    return name || fallbackName || "";
}

function contactNameFromPath(filePath, i18n) {
    var name = fileNameFromPath(filePath, "");
    var dotIndex = name.lastIndexOf(".");
    if (dotIndex > 0)
        name = name.slice(0, dotIndex);

    return name || tr(i18n, "Contact");
}

function canReplyToMessage(message) {
    return !!message && !!message.id && message.id.indexOf("pending-") !== 0;
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
            return;
        }
    }
    messageList.push(message);
}

function isLocalOnlyMessage(message) {
    var messageId = message && message.id ? message.id : "";
    return messageId.indexOf("pending-") === 0 || messageId.indexOf("failed-") === 0 || message.send_status === "pending" || message.send_status === "failed";
}

function mergeRefreshedMessages(currentMessages, refreshedMessages) {
    var mergedMessages = refreshedMessages.slice();
    var knownIds = {};
    var knownTempIds = {};
    for (var i = 0; i < refreshedMessages.length; i++) {
        var refreshed = refreshedMessages[i];
        if (refreshed.id)
            knownIds[refreshed.id] = true;

        if (refreshed.temp_id)
            knownTempIds[refreshed.temp_id] = true;
    }
    var oldestRefreshed = refreshedMessages.length > 0 ? refreshedMessages[0] : null;
    for (var j = 0; j < currentMessages.length; j++) {
        var existing = currentMessages[j];
        var existingId = existing.id || "";
        var existingTempId = existing.temp_id || "";
        if ((existingId !== "" && (knownIds[existingId] || knownTempIds[existingId])) || (existingTempId !== "" && (knownIds[existingTempId] || knownTempIds[existingTempId])))
            continue;

        if (isLocalOnlyMessage(existing) || (oldestRefreshed && messageComesBefore(existing, oldestRefreshed)))
            insertMessageSorted(mergedMessages, existing);
    }
    return mergedMessages;
}

function applyDraftUpdates(chats, updatedDrafts) {
    var newChats = chats.slice();
    var changed = false;
    for (var i = 0; i < updatedDrafts.length; i++) {
        var updatedDraft = updatedDrafts[i];
        for (var j = 0; j < newChats.length; j++) {
            if (newChats[j].id === updatedDraft.id) {
                newChats[j].draft = updatedDraft.draft || "";
                newChats[j].has_draft = !!updatedDraft.has_draft;
                changed = true;
                break;
            }
        }
    }
    return {
        "changed": changed,
        "chats": newChats
    };
}
