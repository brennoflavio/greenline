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
    readonly property bool atBottom: messageList.atYEnd

    signal replyRequested(var message)
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
                messageList.positionViewAtIndex(i, ListView.Beginning);
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
        messageList.positionViewAtEnd();
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
                    if (type === "text") {
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
            text: msg.text || ""
            isOutgoing: msg.is_outgoing || false
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
        }

    }

    Component {
        id: richTextComponent

        MessageBubble {
            copyableText: msg.text || ""
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            senderName: msg.sender_name || ""
            senderPhoto: msg.sender_photo || ""
            replyToId: msg.reply_to_id || ""
            replyToSender: msg.reply_to_sender || ""
            replyToText: msg.reply_to_text || ""
            onReplyClicked: root.scrollToMessage(messageId)

            Label {
                text: msg.text || ""
                fontSize: "small"
                color: "#303030"
                wrapMode: Text.WordWrap
                width: parent.width
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
            isOutgoing: msg.is_outgoing || false
            isGroup: root.isGroup
            timestamp: msg.timestamp || ""
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
