import Lomiri.Components 1.3
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
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
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
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
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
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
        }

    }

    Component {
        id: videoComponent

        VideoMessage {
            thumbnailSource: msg.thumbnail_path || ""
            mediaPath: msg.media_path || ""
            caption: msg.caption || ""
            isOutgoing: msg.is_outgoing || false
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
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
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
            downloading: downloadingIds[msg.id] || false
            onDownloadRequested: triggerDownload(msg.id, "audio")
        }

    }

    Component {
        id: documentComponent

        DocumentMessage {
            fileName: msg.file_name || ""
            mediaPath: msg.media_path || ""
            isOutgoing: msg.is_outgoing || false
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
            sendStatus: msg.send_status || ""
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
            timestamp: msg.timestamp || ""
            downloading: downloadingIds[msg.id] || false
            onDownloadRequested: triggerDownload(msg.id, "sticker")
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
                name: "attachment"
                width: units.gu(3)
                height: units.gu(3)
                color: theme.palette.normal.backgroundSecondaryText
                Layout.alignment: Qt.AlignVCenter

                MouseArea {
                    anchors.fill: parent
                }

            }

            TextField {
                id: messageInput

                Layout.fillWidth: true
                placeholderText: i18n.tr("Type a message...")
            }

            Icon {
                name: messageInput.text.length > 0 ? "send" : "audio-input-microphone-symbolic"
                width: units.gu(3)
                height: units.gu(3)
                color: LomiriColors.green
                Layout.alignment: Qt.AlignVCenter

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
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
                setHandler('message-upsert', function(message) {
                    if (message.chat_id !== chatId)
                        return ;

                    var found = false;
                    var updated = messages.map(function(m) {
                        if (m.id === message.id || (message.temp_id && m.id === message.temp_id)) {
                            found = true;
                            return message;
                        }
                        return m;
                    });
                    if (found) {
                        messages = updated;
                    } else {
                        var newMessages = messages.slice();
                        newMessages.push(message);
                        messages = newMessages;
                    }
                    messagesChanged();
                    if (!message.is_outgoing && !found)
                        python.call('main.mark_messages_as_read', [chatId], function() {
                    });

                });
            });
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
