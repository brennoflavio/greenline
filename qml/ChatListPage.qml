import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7
import QtQuick.Layouts 1.3
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: chatListPage

    property var chats: []

    function messagePreview(msg) {
        if (msg.text)
            return msg.text;

        if (msg.caption)
            return msg.caption;

        var previews = {
            "image": "📷 Photo",
            "image_gallery": "📷 Photo",
            "video": "🎥 Video",
            "audio": "🎵 Audio",
            "voice": "🎵 Audio",
            "document": "📄 Document",
            "sticker": "🏷️ Sticker"
        };
        return previews[msg.type] || msg.type;
    }

    Column {
        anchors {
            top: chatListPage.header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        LoadingBar {
            id: loadingBar

            width: parent.width
            isLoading: false
        }

        Item {
            id: searchBar

            width: parent.width
            height: units.gu(5)

            Row {
                spacing: units.gu(1)

                anchors {
                    fill: parent
                    leftMargin: units.gu(2)
                    rightMargin: units.gu(2)
                }

                Icon {
                    anchors.verticalCenter: parent.verticalCenter
                    name: "find"
                    height: units.gu(2)
                    width: units.gu(2)
                    color: theme.palette.normal.backgroundSecondaryText
                }

                TextField {
                    id: searchInput

                    width: parent.width - units.gu(5)
                    anchors.verticalCenter: parent.verticalCenter
                    placeholderText: i18n.tr("Search chats...")
                }

            }

        }

        ListView {
            id: chatListView

            width: parent.width
            height: parent.height - searchBar.height - loadingBar.height
            clip: true
            model: {
                if (searchInput.text.length === 0)
                    return chats;

                return chats.filter(function(chat) {
                    return chat.name.toLowerCase().indexOf(searchInput.text.toLowerCase()) !== -1;
                });
            }

            delegate: ListItem {
                height: units.gu(8)
                onClicked: {
                    pageStack.push(Qt.resolvedUrl("ChatPage.qml"), {
                        "chatId": modelData.id,
                        "chatName": modelData.name,
                        "chatPhoto": modelData.photo,
                        "isGroup": modelData.is_group || false,
                        "unreadCount": modelData.unread_count || 0
                    });
                }

                RowLayout {
                    spacing: units.gu(1.5)

                    anchors {
                        fill: parent
                        leftMargin: units.gu(2)
                        rightMargin: units.gu(2)
                        topMargin: units.gu(1)
                        bottomMargin: units.gu(1)
                    }

                    Rectangle {
                        width: units.gu(6)
                        height: units.gu(6)
                        radius: width / 2
                        color: theme.palette.normal.base
                        Layout.alignment: Qt.AlignVCenter

                        Image {
                            id: avatarImage

                            anchors.fill: parent
                            source: modelData.photo || ""
                            fillMode: Image.PreserveAspectCrop
                            visible: false
                        }

                        Rectangle {
                            id: avatarMask

                            anchors.fill: parent
                            radius: width / 2
                            visible: false
                        }

                        OpacityMask {
                            anchors.fill: parent
                            source: avatarImage
                            maskSource: avatarMask
                            visible: !!modelData.photo
                        }

                        Icon {
                            anchors.centerIn: parent
                            name: "contact"
                            width: units.gu(3)
                            height: units.gu(3)
                            color: theme.palette.normal.backgroundSecondaryText
                            visible: !modelData.photo
                        }

                    }

                    Column {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: units.gu(0.3)

                        RowLayout {
                            width: parent.width

                            Label {
                                text: modelData.name || ""
                                fontSize: "medium"
                                font.bold: modelData.unread_count > 0
                                color: theme.palette.normal.foregroundText
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            Icon {
                                name: "audio-volume-muted"
                                height: units.gu(2)
                                width: units.gu(2)
                                color: theme.palette.normal.backgroundTertiaryText
                                visible: !!modelData.muted
                                Layout.alignment: Qt.AlignRight
                            }

                            Label {
                                text: modelData.date || ""
                                fontSize: "x-small"
                                color: modelData.unread_count > 0 ? LomiriColors.green : theme.palette.normal.backgroundTertiaryText
                                Layout.alignment: Qt.AlignRight
                            }

                        }

                        RowLayout {
                            width: parent.width

                            Row {
                                spacing: units.gu(0.3)
                                Layout.fillWidth: true

                                Icon {
                                    id: receiptIcon

                                    name: modelData.read_receipt === "sent" ? "message-sent" : "tick"
                                    height: units.gu(1.6)
                                    width: units.gu(1.6)
                                    color: modelData.read_receipt === "read" ? LomiriColors.lightBlue : theme.palette.normal.backgroundTertiaryText
                                    visible: modelData.read_receipt === "sent" || modelData.read_receipt === "delivered" || modelData.read_receipt === "read"
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                                Label {
                                    text: modelData.last_message || ""
                                    fontSize: "small"
                                    color: theme.palette.normal.backgroundTertiaryText
                                    elide: Text.ElideRight
                                    maximumLineCount: 1
                                    width: parent.parent.width - (receiptIcon.visible ? units.gu(2) : 0) - parent.spacing - (unreadBadge.visible ? unreadBadge.width + units.gu(0.5) : 0)
                                    anchors.verticalCenter: parent.verticalCenter
                                }

                            }

                            Rectangle {
                                id: unreadBadge

                                width: units.gu(2.5)
                                height: units.gu(2.5)
                                radius: width / 2
                                color: LomiriColors.green
                                visible: modelData.unread_count > 0
                                Layout.alignment: Qt.AlignRight

                                Label {
                                    anchors.centerIn: parent
                                    text: modelData.unread_count
                                    fontSize: "x-small"
                                    color: "white"
                                    font.bold: true
                                }

                            }

                        }

                    }

                }

                leadingActions: ListItemActions {
                    actions: [
                        Action {
                            iconName: modelData.muted ? "audio-volume-high" : "audio-volume-muted"
                            text: modelData.muted ? i18n.tr("Unmute") : i18n.tr("Mute")
                            onTriggered: {
                                python.call('main.toggle_mute', [modelData.id]);
                            }
                        }
                    ]
                }

            }

        }

        Label {
            visible: chatListView.model.length === 0
            anchors.horizontalCenter: parent.horizontalCenter
            text: i18n.tr("No chats found")
            fontSize: "large"
            color: theme.palette.normal.backgroundSecondaryText
        }

    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                python.call('main.get_sync_status', [], function(syncing) {
                    loadingBar.isLoading = syncing;
                });
                python.call('main.get_chat_list', [], function(result) {
                    if (result.success)
                        chats = result.chats;

                });
                setHandler('sync-status', function(syncing) {
                    loadingBar.isLoading = syncing;
                });
                setHandler('message-upsert', function(messages) {
                    var newChats = chats.slice();
                    for (var i = 0; i < messages.length; i++) {
                        var message = messages[i];
                        for (var j = 0; j < newChats.length; j++) {
                            var chat = newChats[j];
                            if (chat.id === message.chat_id && message.timestamp_unix >= chat.last_message_timestamp) {
                                chat.last_message = messagePreview(message);
                                chat.date = message.timestamp;
                                chat.last_message_timestamp = message.timestamp_unix;
                                chat.read_receipt = message.is_outgoing ? message.read_receipt : "";
                            }
                        }
                    }
                    newChats.sort(function(a, b) {
                        return b.last_message_timestamp - a.last_message_timestamp;
                    });
                    chats = newChats;
                });
                setHandler('chat-list-update', function(updatedChats) {
                    var chatMap = {
                    };
                    for (var i = 0; i < chats.length; i++) chatMap[chats[i].id] = chats[i]
                    for (var j = 0; j < updatedChats.length; j++) chatMap[updatedChats[j].id] = updatedChats[j]
                    var newChats = Object.keys(chatMap).map(function(key) {
                        return chatMap[key];
                    });
                    newChats.sort(function(a, b) {
                        return b.last_message_timestamp - a.last_message_timestamp;
                    });
                    chats = newChats;
                });
            });
        }
    }

    header: AppHeader {
        pageTitle: "Greenline"
        isRootPage: true
        appIconName: "call-start"
        showSettingsButton: true
        onSettingsClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))
    }

}
