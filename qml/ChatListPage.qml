import Lomiri.Components 1.3
import QtQuick 2.7
import "components"
import io.thp.pyotherside 1.4
import "lib/ChatHelpers.js" as ChatHelpers
import "ut_components"

Page {
    id: chatListPage

    property var chats: []
    property bool pythonReady: false
    property bool shareSelectionMode: false
    property bool shareSendInProgress: false
    property string shareFilePath: ""
    property string shareMediaType: ""
    property string shareSelectionTitle: i18n.tr("Share to chat")

    function openChatPage(chat) {
        pageStack.push(Qt.resolvedUrl("ChatPage.qml"), {
            "chatId": chat.id,
            "chatName": chat.name,
            "chatPhoto": chat.photo,
            "isGroup": chat.is_group || false,
            "initialUnreadCount": chat.unread_count || 0
        });
    }

    function sendSharedMedia(chat) {
        if (shareSendInProgress)
            return ;

        if (shareFilePath === "") {
            toast.show(i18n.tr("The shared file is no longer available"));
            return ;
        }
        var sendFunction = "";
        if (shareMediaType === "image") {
            sendFunction = "main.send_image_message";
        } else if (shareMediaType === "video") {
            sendFunction = "main.send_video_message";
        } else if (shareMediaType === "document") {
            sendFunction = "main.send_document_message";
        } else {
            toast.show(i18n.tr("Unsupported shared item"));
            return ;
        }
        shareSendInProgress = true;
        python.call(sendFunction, [chat.id, shareFilePath, "", "pending-" + Date.now(), null], function(result) {
            if (result && !result.success) {
                shareSendInProgress = false;
                toast.show(result.message || i18n.tr("Failed to share file"));
                return ;
            }
            pageStack.pop();
            openChatPage(chat);
        });
    }

    function refreshChatList() {
        python.call('main.get_chat_list', [], function(result) {
            if (result.success)
                chats = result.chats;

        });
    }

    function refreshPageState() {
        if (!pythonReady)
            return ;

        python.call('main.get_sync_status', [], function(syncing) {
            loadingBar.isLoading = syncing;
        });
        refreshChatList();
    }

    function applyDraftUpdates(updatedDrafts) {
        var result = ChatHelpers.applyDraftUpdates(chats, updatedDrafts);
        if (result.changed)
            chats = result.chats;

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

        ChatListSearchBar {
            id: searchBar

            width: parent.width
        }

        ListView {
            id: chatListView

            width: parent.width
            height: parent.height - searchBar.height - loadingBar.height
            clip: true
            model: {
                if (searchBar.text.length === 0)
                    return chats;

                return chats.filter(function(chat) {
                    return chat.name.toLowerCase().indexOf(searchBar.text.toLowerCase()) !== -1;
                });
            }

            delegate: ChatListItem {
                width: chatListView.width
                chat: modelData
                enabled: !chatListPage.shareSendInProgress
                swipeActionsEnabled: !chatListPage.shareSelectionMode
                onClicked: {
                    if (chatListPage.shareSelectionMode)
                        sendSharedMedia(modelData);
                    else
                        openChatPage(modelData);
                }
                onMuteRequested: python.call('main.toggle_mute', [chatId])
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

    Connections {
        target: Qt.application
        onStateChanged: {
            if (Qt.application.state === Qt.ApplicationActive)
                refreshPageState();

        }
    }

    Toast {
        id: toast
    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                pythonReady = true;
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
                                chat.last_message = ChatHelpers.messagePreview(message, i18n);
                                chat.last_message_type = message.type || "";
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
                    refreshChatList();
                });
                setHandler('chat-draft-update', function(updatedDrafts) {
                    applyDraftUpdates(updatedDrafts);
                });
                refreshPageState();
            });
        }
    }

    header: AppHeader {
        pageTitle: chatListPage.shareSelectionMode ? chatListPage.shareSelectionTitle : "Greenline"
        isRootPage: !chatListPage.shareSelectionMode
        appIconName: "call-start"
        showSettingsButton: !chatListPage.shareSelectionMode
        onSettingsClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))
    }

}
