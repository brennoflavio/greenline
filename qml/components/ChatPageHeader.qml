import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7

PageHeader {
    id: root

    property string chatName: ""
    property string chatPhoto: ""
    property string chatStatus: ""

    signal backRequested()
    signal profileRequested()

    leadingActionBar.actions: [
        Action {
            iconName: "back"
            text: i18n.tr("Back")
            onTriggered: root.backRequested()
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
                source: root.chatPhoto || ""
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
                visible: !!root.chatPhoto
            }

            Icon {
                anchors.centerIn: parent
                name: "contact"
                width: units.gu(2.5)
                height: units.gu(2.5)
                color: theme.palette.normal.backgroundSecondaryText
                visible: !root.chatPhoto
            }

            MouseArea {
                anchors.fill: parent
                onClicked: root.profileRequested()
            }

        }

        Column {
            anchors.verticalCenter: parent.verticalCenter

            Label {
                text: root.chatName
                fontSize: "medium"
                font.bold: true
            }

            Label {
                text: root.chatStatus
                fontSize: "x-small"
                color: theme.palette.normal.backgroundTertiaryText
                visible: root.chatStatus !== ""
            }

        }

    }

}
