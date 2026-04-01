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

        }

    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                python.call('main.get_chat_list', [], function(result) {
                    if (!result.success)
                        return ;

                    for (var i = 0; i < result.chats.length; i++) {
                        if (result.chats[i].id === chatId) {
                            muted = !!result.chats[i].muted;
                            break;
                        }
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
