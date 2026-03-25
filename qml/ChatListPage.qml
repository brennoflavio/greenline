import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7
import QtQuick.Layouts 1.3
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: chatListPage

    property var chats: []

    Column {
        anchors {
            top: chatListPage.header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
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
            height: parent.height - searchBar.height
            clip: true
            model: {
                if (searchInput.text.length === 0)
                    return chats;

                return chats.filter(function(chat) {
                    return chat.name.toLowerCase().indexOf(searchInput.text.toLowerCase()) !== -1;
                });
            }

            delegate: Item {
                width: parent.width
                height: units.gu(8)

                Rectangle {
                    id: chatBackground

                    anchors.fill: parent
                    color: "transparent"

                    MouseArea {
                        anchors.fill: parent
                        onPressed: chatBackground.color = theme.palette.highlighted.background
                        onReleased: chatBackground.color = "transparent"
                        onCanceled: chatBackground.color = "transparent"
                        onClicked: {
                            pageStack.push(Qt.resolvedUrl("ChatPage.qml"), {
                                "chatId": modelData.id,
                                "chatName": modelData.name,
                                "chatPhoto": modelData.photo
                            });
                        }
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

                                        name: "tick"
                                        height: units.gu(1.6)
                                        width: units.gu(1.6)
                                        color: modelData.read_receipt === "read" ? LomiriColors.blue : theme.palette.normal.backgroundTertiaryText
                                        visible: modelData.read_receipt === "sent" || modelData.read_receipt === "delivered" || modelData.read_receipt === "read"
                                        anchors.verticalCenter: parent.verticalCenter
                                    }

                                    Label {
                                        text: modelData.last_message || ""
                                        fontSize: "small"
                                        color: theme.palette.normal.backgroundTertiaryText
                                        elide: Text.ElideRight
                                        width: parent.parent.width - (receiptIcon.visible ? units.gu(2) : 0) - parent.spacing
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

                }

                Rectangle {
                    height: units.dp(1)
                    color: theme.palette.normal.base

                    anchors {
                        bottom: parent.bottom
                        left: parent.left
                        right: parent.right
                        leftMargin: units.gu(9.5)
                        rightMargin: units.gu(2)
                    }

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
                python.call('main.get_chat_list', [], function(result) {
                    if (result.success)
                        chats = result.chats;

                });
                setHandler('new-message', function(message) {
                    var updated = false;
                    var newChats = chats.map(function(chat) {
                        if (chat.id === message.chat_id) {
                            updated = true;
                            chat.last_message = message.text || message.caption || message.type;
                            chat.date = message.timestamp;
                            chat.last_message_timestamp = message.timestamp_unix;
                            if (!message.is_outgoing)
                                chat.unread_count = (chat.unread_count || 0) + 1;

                            chat.read_receipt = message.is_outgoing ? message.read_receipt : "";
                        }
                        return chat;
                    });
                    newChats.sort(function(a, b) {
                        return b.last_message_timestamp - a.last_message_timestamp;
                    });
                    chats = newChats;
                });
                setHandler('message-status-update', function(update) {
                    chats = chats.map(function(chat) {
                        if (chat.id === update.chat_id)
                            chat.read_receipt = update.read_receipt;

                        return chat;
                    });
                    chatsChanged();
                });
                setHandler('chat-list-update', function(updatedChat) {
                    var found = false;
                    var newChats = chats.map(function(chat) {
                        if (chat.id === updatedChat.id) {
                            found = true;
                            return updatedChat;
                        }
                        return chat;
                    });
                    if (!found)
                        newChats.unshift(updatedChat);

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
