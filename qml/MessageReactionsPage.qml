import Lomiri.Components 1.3
import QtQuick 2.7
import "components"
import io.thp.pyotherside 1.4
import "lib"

Page {
    id: reactionsPage

    property string chatId: ""
    property string chatName: ""
    property string messageId: ""
    property var reactions: []
    property bool loading: false
    property bool pythonReady: false
    property string errorMessage: ""
    property bool sendingReaction: false
    property int toastDurationMs: 2000
    readonly property bool canSendReaction: pythonReady && !sendingReaction && chatId !== "" && messageId !== ""

    function compareReactionStrings(left, right) {
        var leftValue = left || "";
        var rightValue = right || "";
        if (leftValue < rightValue)
            return -1;

        if (leftValue > rightValue)
            return 1;

        return 0;
    }

    function sortReactions(items) {
        items.sort(function(left, right) {
            var nameComparison = compareReactionStrings(left.name, right.name);
            if (nameComparison !== 0)
                return nameComparison;

            var jidComparison = compareReactionStrings(left.jid, right.jid);
            if (jidComparison !== 0)
                return jidComparison;

            return compareReactionStrings(left.emoji, right.emoji);
        });
        return items;
    }

    function upsertReaction(update) {
        if (!update || !update.jid)
            return ;

        var nextReactions = reactions.slice(0);
        var updatedReaction = {
            "jid": update.jid || "",
            "name": update.name || "",
            "photo": update.photo || "",
            "emoji": update.emoji || "",
            "is_self": !!update.is_self
        };
        var existingIndex = -1;
        for (var i = 0; i < nextReactions.length; i++) {
            if (nextReactions[i] && nextReactions[i].jid === updatedReaction.jid) {
                existingIndex = i;
                break;
            }
        }
        if (existingIndex === -1)
            nextReactions.push(updatedReaction);
        else
            nextReactions[existingIndex] = updatedReaction;
        reactions = sortReactions(nextReactions);
        errorMessage = "";
    }

    function removeReaction(jid) {
        if (!jid)
            return ;

        var nextReactions = [];
        for (var i = 0; i < reactions.length; i++) {
            var reaction = reactions[i];
            if (reaction && reaction.jid !== jid)
                nextReactions.push(reaction);

        }
        reactions = nextReactions;
        errorMessage = "";
    }

    function applyReactionUpdate(update) {
        if (!update || update.chat_id !== chatId || update.message_id !== messageId)
            return ;

        if (update.removed)
            removeReaction(update.jid);
        else
            upsertReaction(update);
    }

    function loadReactions() {
        if (!pythonReady || chatId === "" || messageId === "")
            return ;

        loading = true;
        errorMessage = "";
        python.call('main.get_message_reactions', [chatId, messageId], function(result) {
            loading = false;
            if (result && result.success) {
                reactions = sortReactions(result.reactions || []);
                return ;
            }
            reactions = [];
            errorMessage = result && result.message ? result.message : i18n.tr("Failed to load reactions");
        });
    }

    function sendReaction(emoji, pendingMessage, successMessage) {
        if (!canSendReaction)
            return ;

        sendingReaction = true;
        toast.duration = toastDurationMs;
        toast.show(pendingMessage);
        python.call('main.send_message_reaction', [chatId, messageId, emoji], function(result) {
            sendingReaction = false;
            if (result && result.success) {
                toast.show(successMessage);
                return ;
            }
            toast.show(result && result.message ? result.message : i18n.tr("Failed to send reaction"));
        });
    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                pythonReady = true;
                setHandler('message-reaction-update', function(updates) {
                    for (var i = 0; i < updates.length; i++) applyReactionUpdate(updates[i])
                });
                setHandler('message-upsert', function(messages) {
                    for (var i = 0; i < messages.length; i++) {
                        var message = messages[i];
                        if (!message || message.chat_id !== chatId || message.id !== messageId)
                            continue;

                        if (!message.has_reactions && reactions.length > 0)
                            reactions = [];
                        else if (message.has_reactions && reactions.length === 0 && !loading)
                            loadReactions();
                        break;
                    }
                });
                loadReactions();
            });
        }
    }

    Item {
        anchors {
            top: reactionsHeader.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        Item {
            id: reactionsContent

            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
                bottom: quickActions.top
            }

            ListView {
                id: reactionsList

                anchors.fill: parent
                clip: true
                model: reactions
                visible: !loading && errorMessage === "" && reactions.length > 0

                delegate: ListItem {
                    width: parent ? parent.width : reactionsList.width
                    height: units.gu(7)
                    divider.visible: true
                    onClicked: {
                        pageStack.push(Qt.resolvedUrl("ChatPage.qml"), {
                            "chatId": modelData.jid,
                            "chatName": modelData.name,
                            "chatPhoto": modelData.photo,
                            "isGroup": false,
                            "initialUnreadCount": 0,
                            "initialFirstUnreadMessageId": ""
                        });
                    }

                    Row {
                        spacing: units.gu(1.5)

                        anchors {
                            fill: parent
                            leftMargin: units.gu(2)
                            rightMargin: units.gu(2)
                        }

                        GenericPhoto {
                            width: units.gu(4.5)
                            height: units.gu(4.5)
                            photoPath: modelData.photo || ""
                            fallbackIconName: "contact"
                            fallbackIconWidth: units.gu(2.2)
                            fallbackIconHeight: units.gu(2.2)
                            avatarColor: theme.palette.normal.base
                            fallbackIconColor: theme.palette.normal.backgroundSecondaryText
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        Column {
                            width: parent.width - emojiLabel.width - units.gu(10)
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: units.gu(0.2)

                            Label {
                                text: modelData.name || modelData.jid || ""
                                fontSize: "medium"
                                elide: Text.ElideRight
                                width: parent.width
                            }

                        }

                        Label {
                            id: emojiLabel

                            text: modelData.emoji || ""
                            fontSize: "large"
                            anchors.verticalCenter: parent.verticalCenter
                        }

                    }

                    leadingActions: ListItemActions {
                        actions: [
                            Action {
                                iconName: "delete"
                                text: i18n.tr("Remove")
                                enabled: reactionsPage.canSendReaction && !!modelData.is_self
                                onTriggered: reactionsPage.sendReaction("", i18n.tr("Deleting reaction…"), i18n.tr("Reaction removed"))
                            }
                        ]
                    }

                }

            }

            Label {
                anchors.centerIn: parent
                text: i18n.tr("Loading reactions…")
                visible: loading
                color: theme.palette.normal.backgroundSecondaryText
            }

            Label {
                anchors.centerIn: parent
                width: parent.width - units.gu(4)
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: errorMessage
                visible: !loading && errorMessage !== ""
                color: LomiriColors.lightRed
            }

            Label {
                anchors.centerIn: parent
                text: i18n.tr("No reactions yet")
                visible: !loading && errorMessage === "" && reactions.length === 0
                color: theme.palette.normal.backgroundSecondaryText
            }

        }

        Rectangle {
            id: quickActions

            color: theme.palette.normal.background
            border.width: 0
            width: parent.width
            height: quickActionsColumn.implicitHeight + units.gu(2)

            anchors {
                left: parent.left
                right: parent.right
                bottom: parent.bottom
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

            Column {
                id: quickActionsColumn

                spacing: units.gu(1)

                anchors {
                    fill: parent
                    margins: units.gu(1)
                }

                Label {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    text: i18n.tr("Quick reactions")
                    color: theme.palette.normal.backgroundSecondaryText
                }

                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: units.gu(0.5)

                    Repeater {
                        model: ["👍", "❤️", "😂", "😮", "🙏"]

                        delegate: Button {
                            width: units.gu(5)
                            text: modelData
                            enabled: reactionsPage.canSendReaction
                            onClicked: reactionsPage.sendReaction(modelData, i18n.tr("Sending reaction…"), i18n.tr("Reaction updated"))
                        }

                    }

                }

            }

        }

        Toast {
            id: toast

            bottomMargin: quickActions.height + units.gu(2)
        }

    }

    header: PageHeader {
        id: reactionsHeader

        title: i18n.tr("Reactions")
        leadingActionBar.actions: [
            Action {
                iconName: "back"
                text: i18n.tr("Back")
                onTriggered: pageStack.pop()
            }
        ]
    }

}
