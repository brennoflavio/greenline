import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import Lomiri.Content 1.3
import QtQuick 2.7
import "components"
import io.thp.pyotherside 1.4
import "lib/ChatHelpers.js" as ChatHelpers
import "ut_components"

Page {
    id: chatListPage

    property var chats: []
    property bool pythonReady: false
    property bool showArchived: false
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
            "initialUnreadCount": chat.unread_count || 0,
            "initialFirstUnreadMessageId": chat.first_unread_message_id || ""
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

    function startChatFromPhone(dialog, phoneNumber) {
        python.call('main.start_chat_by_phone', [phoneNumber], function(result) {
            if (result && result.success && result.chat) {
                PopupUtils.close(dialog);
                openChatPage(result.chat);
                return ;
            }
            if (dialog)
                dialog.opening = false;

            toast.show(result && result.message ? result.message : i18n.tr("Failed to start chat"));
        });
    }

    function startChatFromContact(filePath) {
        python.call('main.start_chat_from_contact', [filePath], function(result) {
            if (result && result.success && result.chat) {
                openChatPage(result.chat);
                return ;
            }
            toast.show(result && result.message ? result.message : i18n.tr("Failed to import contact"));
        });
    }

    function openContactImportPicker() {
        pageStack.push(contactPickerPage);
    }

    function refreshChatList() {
        python.call('main.get_chat_list', [showArchived], function(result) {
            if (result.success)
                updateChats(result.chats, false);

        });
    }

    function switchListMode(targetArchived) {
        if (shareSelectionMode || showArchived === targetArchived)
            return ;

        pageStack.clear();
        pageStack.push(Qt.resolvedUrl("ChatListPage.qml"), {
            "showArchived": targetArchived
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

    function updateChats(nextChats, preserveScrollPosition) {
        var previousContentY = preserveScrollPosition ? chatListView.contentY : 0;
        chats = nextChats;
        if (!preserveScrollPosition)
            return ;

        Qt.callLater(function() {
            var maxContentY = Math.max(0, chatListView.contentHeight - chatListView.height);
            chatListView.contentY = Math.min(previousContentY, maxContentY);
        });
    }

    function applyDraftUpdates(updatedDrafts) {
        var result = ChatHelpers.applyDraftUpdates(chats, updatedDrafts);
        if (result.changed)
            updateChats(result.chats, true);

    }

    function loadChatDraft(chatId) {
        python.call('main.get_chat_draft', [chatId], function(result) {
            if (!result || !result.success || !result.text)
                return ;

            applyDraftUpdates([{
                "id": chatId,
                "draft": result.text,
                "has_draft": true
            }]);
        });
    }

    function applyMessageUpserts(messages) {
        if (messages.length === 0 || chats.length === 0)
            return ;

        var newChats = chats.slice();
        var chatIndexes = {
        };
        for (var i = 0; i < newChats.length; i++) chatIndexes[newChats[i].id] = i
        var changed = false;
        for (var j = 0; j < messages.length; j++) {
            var message = messages[j];
            var chatIndex = chatIndexes.hasOwnProperty(message.chat_id) ? chatIndexes[message.chat_id] : -1;
            if (chatIndex === -1)
                continue;

            var chat = newChats[chatIndex];
            if (message.timestamp_unix < chat.last_message_timestamp)
                continue;

            var nextLastMessage = ChatHelpers.messagePreview(message, i18n);
            var nextLastMessageType = message.type || "";
            var nextDate = message.timestamp;
            var nextTimestamp = message.timestamp_unix;
            var nextReadReceipt = message.is_outgoing ? message.read_receipt : "";
            if (chat.last_message === nextLastMessage && chat.last_message_type === nextLastMessageType && chat.date === nextDate && chat.last_message_timestamp === nextTimestamp && chat.read_receipt === nextReadReceipt)
                continue;

            var updatedChat = Object.assign({
            }, chat, {
                "last_message": nextLastMessage,
                "last_message_type": nextLastMessageType,
                "date": nextDate,
                "last_message_timestamp": nextTimestamp,
                "read_receipt": nextReadReceipt
            });
            if (chat.last_message_timestamp !== nextTimestamp) {
                newChats.splice(chatIndex, 1);
                var replacementIndex = ChatHelpers.insertChatSorted(newChats, updatedChat);
                var reindexStart = Math.min(chatIndex, replacementIndex);
                for (var k = reindexStart; k < newChats.length; k++) chatIndexes[newChats[k].id] = k
            } else {
                newChats[chatIndex] = updatedChat;
            }
            changed = true;
        }
        if (changed)
            updateChats(newChats, true);

    }

    Column {
        anchors {
            top: chatListPage.header.bottom
            left: parent.left
            right: parent.right
            bottom: bottomBar.visible ? bottomBar.top : parent.bottom
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
                onArchiveRequested: python.call('main.toggle_archive', [chatId])
            }

        }

        Label {
            visible: chatListView.model.length === 0
            anchors.horizontalCenter: parent.horizontalCenter
            text: chatListPage.showArchived ? i18n.tr("No archived chats") : i18n.tr("No chats found")
            fontSize: "large"
            color: theme.palette.normal.backgroundSecondaryText
        }

    }

    BottomBar {
        id: bottomBar

        visible: !chatListPage.shareSelectionMode

        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        IconButton {
            iconName: "contact-group"
            text: i18n.tr("Chats")
            onClicked: chatListPage.switchListMode(false)
        }

        IconButton {
            iconName: "add"
            text: i18n.tr("New")
            enabled: chatListPage.pythonReady
            onClicked: PopupUtils.open(newChatDialog, chatListPage)
        }

        IconButton {
            iconName: "document-save"
            text: i18n.tr("Archived")
            onClicked: chatListPage.switchListMode(true)
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

    Component {
        id: newChatDialog

        NewChatDialog {
            id: dialog

            onChatRequested: chatListPage.startChatFromPhone(dialog, phoneNumber)
            onImportRequested: chatListPage.openContactImportPicker()
        }

    }

    Component {
        id: contactPickerPage

        ChatAttachmentPickerPage {
            pickerTitle: i18n.tr("Import Contact")
            pickerContentType: ContentType.Contacts
            onFileSelected: chatListPage.startChatFromContact(filePath)
        }

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
                    applyMessageUpserts(messages);
                });
                setHandler('chat-list-update', function(updatedChats) {
                    var knownChatIds = {
                    };
                    for (var i = 0; i < chats.length; i++) knownChatIds[chats[i].id] = true
                    var result = ChatHelpers.applyChatListUpdates(chats, updatedChats, showArchived);
                    if (result.changed)
                        updateChats(result.chats, true);

                    for (var j = 0; j < updatedChats.length; j++) {
                        var updatedChat = updatedChats[j];
                        if (!knownChatIds[updatedChat.id] && !!updatedChat.archived === showArchived) {
                            knownChatIds[updatedChat.id] = true;
                            loadChatDraft(updatedChat.id);
                        }
                    }
                });
                setHandler('chat-draft-update', function(updatedDrafts) {
                    applyDraftUpdates(updatedDrafts);
                });
                refreshPageState();
            });
        }
    }

    header: AppHeader {
        pageTitle: chatListPage.shareSelectionMode ? chatListPage.shareSelectionTitle : (chatListPage.showArchived ? i18n.tr("Archived") : i18n.tr("Chats"))
        isRootPage: !chatListPage.shareSelectionMode
        appIconName: "call-start"
        showSettingsButton: !chatListPage.shareSelectionMode
        onSettingsClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))
    }

}
