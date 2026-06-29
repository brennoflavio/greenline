import Lomiri.Components 1.3
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

        GenericPhoto {
            width: units.gu(4.5)
            height: units.gu(4.5)
            photoPath: root.chatPhoto || ""
            fallbackIconName: "contact"
            fallbackIconWidth: units.gu(2.5)
            fallbackIconHeight: units.gu(2.5)
            avatarColor: theme.palette.normal.base
            fallbackIconColor: theme.palette.normal.backgroundSecondaryText
            anchors.verticalCenter: parent.verticalCenter

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
