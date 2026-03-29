import Lomiri.Components 1.3
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

                if (msg.type === "voice")
                    return voiceComponent;

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
        }

    }

    Component {
        id: imageComponent

        ImageMessage {
            imageSource: msg.image_source || ""
            caption: msg.caption || ""
            isOutgoing: msg.is_outgoing || false
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
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
        }

    }

    Component {
        id: voiceComponent

        VoiceMessage {
            duration: msg.duration || "0:00"
            isOutgoing: msg.is_outgoing || false
            timestamp: msg.timestamp || ""
            readReceipt: msg.read_receipt || ""
        }

    }

    Component {
        id: stickerComponent

        StickerMessage {
            stickerSource: msg.sticker_source || ""
            isOutgoing: msg.is_outgoing || false
            timestamp: msg.timestamp || ""
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
                setHandler('new-message', function(message) {
                    if (message.chat_id !== chatId)
                        return ;

                    var newMessages = messages.slice();
                    newMessages.push(message);
                    messages = newMessages;
                    if (!message.is_outgoing)
                        python.call('main.mark_messages_as_read', [chatId], function() {
                    });

                });
                setHandler('message-status-update', function(updated) {
                    if (updated.chat_id !== chatId)
                        return ;

                    messages = messages.map(function(msg) {
                        if (msg.id === updated.id)
                            return updated;

                        return msg;
                    });
                    messagesChanged();
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
