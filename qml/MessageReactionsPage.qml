import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7
import io.thp.pyotherside 1.4

Page {
    id: reactionsPage

    property string chatId: ""
    property string chatName: ""
    property string messageId: ""
    property var reactions: []
    property bool loading: false
    property bool pythonReady: false
    property string errorMessage: ""

    function loadReactions() {
        if (!pythonReady || chatId === "" || messageId === "")
            return ;

        loading = true;
        errorMessage = "";
        python.call('main.get_message_reactions', [chatId, messageId], function(result) {
            loading = false;
            if (result && result.success) {
                reactions = result.reactions || [];
                return ;
            }
            reactions = [];
            errorMessage = result && result.message ? result.message : i18n.tr("Failed to load reactions");
        });
    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                pythonReady = true;
                setHandler('message-upsert', function(messages) {
                    for (var i = 0; i < messages.length; i++) {
                        var message = messages[i];
                        if (message && message.chat_id === chatId && message.id === messageId) {
                            loadReactions();
                            break;
                        }
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
                        "initialUnreadCount": 0
                    });
                }

                Row {
                    spacing: units.gu(1.5)

                    anchors {
                        fill: parent
                        leftMargin: units.gu(2)
                        rightMargin: units.gu(2)
                    }

                    Rectangle {
                        width: units.gu(4.5)
                        height: units.gu(4.5)
                        radius: width / 2
                        color: theme.palette.normal.base
                        anchors.verticalCenter: parent.verticalCenter

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
                            width: units.gu(2.2)
                            height: units.gu(2.2)
                            color: theme.palette.normal.backgroundSecondaryText
                            visible: !modelData.photo
                        }

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
