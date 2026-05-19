.pragma library

function cloneSpan(span) {
    return {
        "jid": String(span.jid || ""),
        "label": String(span.label || ""),
        "start": Number(span.start || 0),
        "length": Number(span.length || 0)
    };
}

function cloneMentionSpans(spans) {
    var cloned = [];
    for (var i = 0; i < (spans || []).length; i++)
        cloned.push(cloneSpan(spans[i] || {}));

    return cloned;
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

function updateMentionSpansForEdit(oldText, newText, mentionSpans) {
    if (!mentionSpans || !mentionSpans.length)
        return [];

    var prefixLength = 0;
    while (prefixLength < oldText.length && prefixLength < newText.length && oldText.charAt(prefixLength) === newText.charAt(prefixLength))
        prefixLength++;

    var suffixLength = 0;
    while (suffixLength < oldText.length - prefixLength && suffixLength < newText.length - prefixLength && oldText.charAt(oldText.length - 1 - suffixLength) === newText.charAt(newText.length - 1 - suffixLength))
        suffixLength++;

    var oldChangeEnd = oldText.length - suffixLength;
    var shift = newText.length - oldText.length;
    var shifted = [];
    for (var i = 0; i < mentionSpans.length; i++) {
        var span = cloneSpan(mentionSpans[i]);
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

function mentionSuggestions(text, cursorPosition, mentionCandidates, maxResults) {
    var textBeforeCursor = (text || "").slice(0, cursorPosition);
    var atIndex = textBeforeCursor.lastIndexOf("@");
    if (atIndex < 0)
        return { "activeMentionStart": -1, "activeMentionQuery": "", "filteredMentionCandidates": [] };

    if (atIndex > 0 && !/\s/.test(textBeforeCursor.charAt(atIndex - 1)))
        return { "activeMentionStart": -1, "activeMentionQuery": "", "filteredMentionCandidates": [] };

    var query = textBeforeCursor.slice(atIndex + 1);
    if (/\s/.test(query))
        return { "activeMentionStart": -1, "activeMentionQuery": "", "filteredMentionCandidates": [] };

    var queryLower = query.toLowerCase();
    var matches = [];
    for (var i = 0; i < (mentionCandidates || []).length; i++) {
        var candidate = mentionCandidates[i];
        var label = String(candidate && candidate.label || "");
        if (!label)
            continue;

        if (queryLower === "" || label.toLowerCase().indexOf(queryLower) !== -1)
            matches.push(candidate);
    }
    return {
        "activeMentionStart": atIndex,
        "activeMentionQuery": query,
        "filteredMentionCandidates": matches.slice(0, maxResults || 5)
    };
}

function insertMention(text, cursorPosition, activeMentionStart, mentionSpans, candidate) {
    var label = String(candidate && candidate.label || "");
    var jid = String(candidate && candidate.jid || "");
    if (!label || !jid || activeMentionStart < 0) {
        return {
            "text": text || "",
            "cursorPosition": cursorPosition,
            "mentionSpans": cloneMentionSpans(mentionSpans)
        };
    }

    var replacement = "@" + label + " ";
    var before = (text || "").slice(0, activeMentionStart);
    var after = (text || "").slice(cursorPosition);
    var newText = before + replacement + after;
    var shift = replacement.length - (cursorPosition - activeMentionStart);
    var nextSpans = [];
    for (var i = 0; i < (mentionSpans || []).length; i++) {
        var span = cloneSpan(mentionSpans[i]);
        var spanEnd = span.start + span.length;
        if (spanEnd <= activeMentionStart) {
            nextSpans.push(span);
            continue;
        }
        if (span.start >= cursorPosition) {
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
    return {
        "text": newText,
        "cursorPosition": before.length + replacement.length,
        "mentionSpans": validateMentionSpans(newText, nextSpans)
    };
}
