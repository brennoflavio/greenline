import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import Lomiri.Content 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7
import QtQuick.Layouts 1.3
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
            "media_path": "file://" + filePath
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesChanged();
        python.call('main.send_video_message', [chatId, filePath, "", tempId], function() {
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
            "media_path": filePath
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesChanged();
        var cleanPath = filePath.toString().replace("file://", "");
        python.call('main.send_sticker_message', [chatId, cleanPath, tempId], function() {
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
            "media_path": "file://" + filePath
        };
        var newMessages = messages.slice();
        newMessages.push(pendingMsg);
        messages = newMessages;
        messagesChanged();
        python.call('main.send_image_message', [chatId, filePath, "", tempId], function() {
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

            var pendingMsg = {
                "id": tempId,
                "chat_id": chatId,
                "type": "text",
                "is_outgoing": true,
                "text": text,
                "timestamp": hours + ":" + minutes,
                "read_receipt": "",
                "send_status": "pending",
                "temp_id": tempId
            };
            var newMessages = messages.slice();
            newMessages.push(pendingMsg);
            messages = newMessages;
            messagesChanged();
            messageInput.text = "";
            python.call('main.send_text_message', [chatId, text, tempId], function() {
            });
        }
    }

    ListView {
        id: messageList

        clip: true
        verticalLayoutDirection: ListView.BottomToTop
        spacing: units.gu(0.5)
        model: messages.slice().reverse()

        anchors {
            top: chatHeader.bottom
            left: parent.left
            right: parent.right
            bottom: inputBar.top
        }

        delegate: Loader {
            property var msg: modelData

            width: parent ? parent.width : 0
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

                if (msg.type === "sticker")
                    return stickerComponent;

                return textComponent;
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
            downloading: downloadingIds[msg.id] || false
            onDownloadRequested: triggerDownload(msg.id, "document")
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
        }

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

        height: units.gu(6)
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

        RowLayout {
            spacing: units.gu(1)

            anchors {
                fill: parent
                leftMargin: units.gu(1)
                rightMargin: units.gu(1)
                topMargin: units.gu(0.5)
                bottomMargin: units.gu(0.5)
            }

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

            TextField {
                id: messageInput

                Layout.fillWidth: true
                placeholderText: i18n.tr("Type a message...")
                onAccepted: sendMessage()
            }

            Icon {
                name: messageInput.text.length > 0 ? "send" : "audio-input-microphone-symbolic"
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

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                python.call('main.get_messages', [chatId], function(result) {
                    if (result.success) {
                        messages = result.messages;
                        python.call('main.mark_messages_as_read', [chatId], function() {
                        });
                    }
                });
                setHandler('message-upsert', function(messageList) {
                    var updated = messages.slice();
                    var hasNewIncoming = false;
                    for (var i = 0; i < messageList.length; i++) {
                        var message = messageList[i];
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
                            if (!message.is_outgoing)
                                hasNewIncoming = true;

                        }
                    }
                    messages = updated;
                    messagesChanged();
                    if (hasNewIncoming)
                        python.call('main.mark_messages_as_read', [chatId], function() {
                    });

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
                    text: i18n.tr("online")
                    fontSize: "x-small"
                    color: theme.palette.normal.backgroundTertiaryText
                }

            }

        }

    }

}
