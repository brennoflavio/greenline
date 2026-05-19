import Lomiri.Components 1.3
import Lomiri.Content 1.3
import QtQuick 2.7
import "ut_components"

Page {
    id: previewPage

    property string contactPath: ""
    property string contactName: ""

    Column {
        spacing: units.gu(2)

        anchors {
            top: previewHeader.bottom
            left: parent.left
            right: parent.right
            bottom: bottomBar.top
            margins: units.gu(4)
            topMargin: units.gu(8)
        }

        Rectangle {
            width: units.gu(10)
            height: units.gu(10)
            radius: units.gu(1)
            color: "#e8e8e8"
            anchors.horizontalCenter: parent.horizontalCenter

            Icon {
                anchors.centerIn: parent
                name: "contact"
                width: units.gu(6)
                height: units.gu(6)
                color: theme.palette.normal.backgroundSecondaryText
            }

        }

        Label {
            text: previewPage.contactName || i18n.tr("Contact")
            fontSize: "large"
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            width: parent.width
        }

        Label {
            text: i18n.tr("Ready to export")
            fontSize: "small"
            color: theme.palette.normal.backgroundTertiaryText
            horizontalAlignment: Text.AlignHCenter
            width: parent.width
        }

    }

    BottomBar {
        id: bottomBar

        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        IconButton {
            iconName: "save"
            text: i18n.tr("Save")
            onClicked: {
                pageStack.push(Qt.resolvedUrl("components/ContentTransferPage.qml"), {
                    "transferUrl": previewPage.contactPath,
                    "transferContentType": ContentType.Documents,
                    "shareMode": false
                });
            }
        }

        IconButton {
            iconName: "share"
            text: i18n.tr("Share")
            onClicked: {
                pageStack.push(Qt.resolvedUrl("components/ContentTransferPage.qml"), {
                    "transferUrl": previewPage.contactPath,
                    "transferContentType": ContentType.Documents,
                    "shareMode": true
                });
            }
        }

    }

    header: PageHeader {
        id: previewHeader

        title: contactName || i18n.tr("Contact")
        leadingActionBar.actions: [
            Action {
                iconName: "back"
                text: i18n.tr("Back")
                onTriggered: pageStack.pop()
            }
        ]
    }

}
