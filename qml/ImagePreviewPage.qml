import Lomiri.Components 1.3
import Lomiri.Content 1.3
import QtQuick 2.7
import "ut_components"

Page {
    id: previewPage

    property string imagePath: ""

    ImageViewer {
        currentItem: previewPage.imagePath
        navigationEnabled: false
        showNavigationButtons: false

        anchors {
            top: previewHeader.bottom
            left: parent.left
            right: parent.right
            bottom: bottomBar.top
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
                    "transferUrl": previewPage.imagePath,
                    "transferContentType": ContentType.Pictures,
                    "shareMode": false
                });
            }
        }

        IconButton {
            iconName: "share"
            text: i18n.tr("Share")
            onClicked: {
                pageStack.push(Qt.resolvedUrl("components/ContentTransferPage.qml"), {
                    "transferUrl": previewPage.imagePath,
                    "transferContentType": ContentType.Pictures,
                    "shareMode": true
                });
            }
        }

    }

    header: PageHeader {
        id: previewHeader

        title: imagePath.split("/").pop() || i18n.tr("Image")
        leadingActionBar.actions: [
            Action {
                iconName: "back"
                text: i18n.tr("Back")
                onTriggered: pageStack.pop()
            }
        ]
    }

}
