import "../ut_components"
import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3

MessageBubble {
    id: root

    property string contactName: ""
    property string mediaPath: ""

    copyableText: contactName

    Item {
        width: parent.width
        height: contactRow.height

        RowLayout {
            id: contactRow

            width: parent.width
            spacing: units.gu(1)

            Rectangle {
                width: units.gu(5)
                height: units.gu(5)
                radius: units.gu(0.5)
                color: "#e8e8e8"
                Layout.alignment: Qt.AlignVCenter

                Icon {
                    anchors.centerIn: parent
                    name: "contact"
                    width: units.gu(3)
                    height: units.gu(3)
                    color: root.mediaPath ? LomiriColors.green : theme.palette.normal.backgroundSecondaryText
                }

            }

            Column {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: units.gu(0.2)

                Label {
                    text: root.contactName || i18n.tr("Contact")
                    fontSize: "small"
                    color: "#303030"
                    wrapMode: Text.WordWrap
                    width: parent.width
                }

                Label {
                    text: root.mediaPath ? i18n.tr("Tap to open") : i18n.tr("Unavailable")
                    fontSize: "x-small"
                    color: "#999999"
                }

            }

        }

        MouseArea {
            anchors.fill: parent
            enabled: !!root.mediaPath
            onClicked: {
                pageStack.push(Qt.resolvedUrl("../ContactPreviewPage.qml"), {
                    "contactPath": root.mediaPath,
                    "contactName": root.contactName
                });
            }
        }

    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
