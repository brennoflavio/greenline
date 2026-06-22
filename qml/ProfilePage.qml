import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7
import QtQuick.Layouts 1.3
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: profilePage

    property string chatId: ""
    property string chatName: ""
    property string chatPhoto: ""
    property bool isGroup: chatId.indexOf("@g.us") !== -1
    property bool muted: false
    property string phoneNumber: ""
    property string groupDescription: ""
    property int memberCount: 0
    property var members: []

    function openMemberChat(member) {
        if (!member || !member.jid)
            return ;

        pageStack.push(Qt.resolvedUrl("ChatPage.qml"), {
            "chatId": member.jid,
            "chatName": member.name || member.jid,
            "chatPhoto": member.photo || "",
            "isGroup": false,
            "initialUnreadCount": 0
        });
    }

    Flickable {
        contentHeight: content.height + units.gu(4)
        clip: true

        anchors {
            top: profilePage.header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        Column {
            id: content

            width: parent.width
            spacing: units.gu(2)
            topPadding: units.gu(3)

            Rectangle {
                width: units.gu(16)
                height: units.gu(16)
                radius: width / 2
                color: theme.palette.normal.base
                anchors.horizontalCenter: parent.horizontalCenter

                Image {
                    id: profileAvatar

                    anchors.fill: parent
                    source: chatPhoto || ""
                    fillMode: Image.PreserveAspectCrop
                    visible: false
                }

                Rectangle {
                    id: profileAvatarMask

                    anchors.fill: parent
                    radius: width / 2
                    visible: false
                }

                OpacityMask {
                    anchors.fill: parent
                    source: profileAvatar
                    maskSource: profileAvatarMask
                    visible: !!chatPhoto
                }

                Icon {
                    anchors.centerIn: parent
                    name: isGroup ? "contact-group" : "contact"
                    width: units.gu(8)
                    height: units.gu(8)
                    color: theme.palette.normal.backgroundSecondaryText
                    visible: !chatPhoto
                }

            }

            Label {
                text: chatName
                fontSize: "x-large"
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                width: parent.width
                wrapMode: Text.WordWrap
            }

            Label {
                text: isGroup ? i18n.tr("Group") : phoneNumber
                fontSize: "medium"
                color: theme.palette.normal.backgroundSecondaryText
                horizontalAlignment: Text.AlignHCenter
                width: parent.width
                visible: isGroup || phoneNumber !== ""
            }

            Item {
                width: parent.width
                height: units.gu(2)
            }

            ConfigurationGroup {
                title: i18n.tr("Settings")

                ToggleOption {
                    title: i18n.tr("Mute notifications")
                    subtitle: i18n.tr("Silence all notifications from this chat")
                    checked: muted
                    onToggled: {
                        muted = checked;
                        python.call('main.toggle_mute', [chatId]);
                    }
                }

            }

            ConfigurationGroup {
                title: i18n.tr("Description")
                visible: isGroup && groupDescription !== ""

                Label {
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignJustify
                    text: groupDescription
                    color: theme.palette.normal.foregroundText

                    anchors {
                        left: parent.left
                        right: parent.right
                        leftMargin: units.gu(2)
                        rightMargin: units.gu(2)
                    }

                }

            }

            ConfigurationGroup {
                title: i18n.tr("Members")
                visible: isGroup && (memberCount > 0 || members.length > 0)

                Label {
                    text: i18n.tr("%1 members").arg(memberCount)
                    color: theme.palette.normal.backgroundSecondaryText

                    anchors {
                        left: parent.left
                        right: parent.right
                        leftMargin: units.gu(2)
                        rightMargin: units.gu(2)
                    }

                }

                Column {
                    width: parent.width

                    Repeater {
                        model: members

                        delegate: ListItem {
                            width: parent ? parent.width : content.width
                            height: units.gu(7)
                            divider.visible: true
                            onClicked: profilePage.openMemberChat(modelData)

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
                                    width: units.gu(4.5)
                                    height: units.gu(4.5)
                                    radius: width / 2
                                    color: theme.palette.normal.base
                                    Layout.alignment: Qt.AlignVCenter

                                    Image {
                                        id: memberAvatar

                                        anchors.fill: parent
                                        source: modelData.photo || ""
                                        fillMode: Image.PreserveAspectCrop
                                        visible: false
                                    }

                                    Rectangle {
                                        id: memberAvatarMask

                                        anchors.fill: parent
                                        radius: width / 2
                                        visible: false
                                    }

                                    OpacityMask {
                                        anchors.fill: parent
                                        source: memberAvatar
                                        maskSource: memberAvatarMask
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

                                Label {
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    text: modelData.name || modelData.jid || ""
                                    fontSize: "medium"
                                    elide: Text.ElideRight
                                }

                            }

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
                python.call('main.get_chat_info', [chatId], function(result) {
                    if (result.success) {
                        chatName = result.name || chatName;
                        chatPhoto = result.photo || "";
                        muted = !!result.muted;
                        groupDescription = result.description || "";
                        memberCount = result.member_count || 0;
                        members = result.members || [];
                    }
                });
                if (!isGroup)
                    python.call('main.get_phone_number', [chatId], function(result) {
                    if (result.success)
                        phoneNumber = result.phone_number;

                });

            });
        }
    }

    header: AppHeader {
        pageTitle: i18n.tr("Profile")
        isRootPage: false
    }

}
