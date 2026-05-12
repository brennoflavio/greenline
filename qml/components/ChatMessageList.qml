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
    property int editWindowSeconds: 20 * 60
    readonly property bool atBottom: messageList.atYEnd

    signal replyRequested(var message)
    signal editRequested(var message)
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

    function canEditMessage(message) {
        var messageId = message && message.id ? message.id : "";
        var timestampUnix = message && message.timestamp_unix ? message.timestamp_unix : 0;
        return !!message && !!message.is_outgoing && messageId !== "" && messageId.indexOf("pending-") !== 0 && messageId.indexOf("failed-") !== 0 && (message.type || "") === "text" && timestampUnix > 0 && Math.floor(Date.now() / 1000) - timestampUnix <= editWindowSeconds;
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
                    var type = msg.type || "text";
                    if (type === "text" || type === "view_once" || type === "deleted") {
                        if (msg.reply_to_id || (root.isGroup && !msg.is_outgoing && (msg.sender_name || "") !== ""))
                            return richTextComponent;

                        return textComponent;
                    }
                    if (type === "image")
                        return imageComponent;

                    if (type === "image_gallery")
                        return galleryComponent;

                    if (type === "video")
                        return videoComponent;

                    if (type === "voice" || type === "audio")
                        return voiceComponent;

                    if (type === "document")
                        return documentComponent;

                    if (type === "contact")
                        return contactComponent;

                    if (type === "sticker")
                        return stickerComponent;

                    if (type === "link_preview")
                        return linkPreviewComponent;

                    if (msg.reply_to_id || (root.isGroup && !msg.is_outgoing && (msg.sender_name || "") !== ""))
                        return richTextComponent;

                    return textComponent;
                }
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
            isOutgoing: msg.is_outgoing || false
            timestamp: msg.timestamp || ""
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
        }

    }

    Component {
        id: richTextComponent

        MessageBubble {
            property bool expandedText: false
            property int collapsedLineCount: 10
            readonly property real senderWidthHint: showSender ? senderMeasure.implicitWidth + units.gu(2) : 0
            readonly property real replyWidthHint: replyToId !== "" ? Math.max(replySenderMeasure.implicitWidth, replyTextMeasure.implicitWidth) + units.gu(3.5) : 0
            readonly property bool shouldCollapse: fullHeightMeasure.implicitHeight > collapsedHeightMeasure.implicitHeight + units.gu(0.1)

            copyableText: root.messageText(msg)
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            preferredBubbleWidth: Math.max(textMeasure.implicitWidth + units.gu(2), senderWidthHint, replyWidthHint)
            onReplyClicked: root.scrollToMessage(messageId)

            Label {
                id: textMeasure

                visible: false
                text: root.messageText(msg)
                fontSize: "small"
            }

            Label {
                id: senderMeasure

                visible: false
                text: msg.sender_name || ""
                fontSize: "x-small"
                font.bold: true
            }

            Label {
                id: replySenderMeasure

                visible: false
                text: msg.reply_to_sender || ""
                fontSize: "small"
                font.bold: true
            }

            Label {
                id: replyTextMeasure

                visible: false
                text: msg.reply_to_text || ""
                fontSize: "small"
            }

            Label {
                id: fullHeightMeasure

                visible: false
                text: root.messageText(msg)
                fontSize: "small"
                wrapMode: Text.Wrap
                width: parent.width
            }

            Label {
                id: collapsedHeightMeasure

                visible: false
                text: root.messageText(msg)
                fontSize: "small"
                wrapMode: Text.Wrap
                width: parent.width
                maximumLineCount: collapsedLineCount
                elide: Text.ElideRight
            }

            Label {
                text: root.messageText(msg)
                fontSize: "small"
                color: "#303030"
                wrapMode: Text.Wrap
                width: parent.width
                maximumLineCount: shouldCollapse && !expandedText ? collapsedLineCount : 2.14748e+09
                elide: shouldCollapse && !expandedText ? Text.ElideRight : Text.ElideNone
            }

            Column {
                visible: shouldCollapse
                width: parent.width
                spacing: 0

                Item {
                    width: 1
                    height: toggleLabel.implicitHeight
                }

                Item {
                    width: parent.width
                    height: toggleLabel.implicitHeight + units.gu(0.6)

                    Label {
                        id: toggleLabel

                        text: expandedText ? i18n.tr("Show less") : i18n.tr("Show more")
                        fontSize: "small"
                        color: LomiriColors.blue

                        anchors {
                            left: parent.left
                            verticalCenter: parent.verticalCenter
                        }

                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: expandedText = !expandedText
                    }

                }

            }

            Item {
                width: 1
                height: units.gu(1.5)
            }

        }

    }

    Component {
        id: imageComponent

        ImageMessage {
            imageSource: msg.image_source || ""
            thumbnailSource: msg.thumbnail_path || ""
            mediaPath: msg.media_path || ""
            caption: msg.caption || ""
            buttonText: msg.button_text || ""
            buttonUrl: msg.button_url || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
            downloading: root.downloadingIds[msg.id] || false
            onDownloadRequested: root.downloadRequested(msg.id, "image")
        }

    }

    Component {
        id: galleryComponent

        ImageGalleryMessage {
            images: msg.images || []
            caption: msg.caption || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
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
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
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
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
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
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
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
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)
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
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            edited: msg.edited || false
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
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
            edited: msg.edited || false
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
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
