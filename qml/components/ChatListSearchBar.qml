import Lomiri.Components 1.3
import QtQuick 2.7

Item {
    id: root

    property alias text: searchInput.text
    property string placeholderText: i18n.tr("Search chats...")

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
            placeholderText: root.placeholderText
        }

    }

}
