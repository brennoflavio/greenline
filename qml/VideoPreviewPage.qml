import Lomiri.Components 1.3
import Lomiri.Content 1.3
import QtQuick 2.7
import "ut_components"

Page {
    id: previewPage

    property string videoPath: ""

    VideoViewer {
        id: videoViewer

        currentItem: previewPage.videoPath
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
                videoViewer.pause();
                pageStack.push(Qt.resolvedUrl("components/ContentTransferPage.qml"), {
                    "transferUrl": previewPage.videoPath,
                    "transferContentType": ContentType.Videos,
                    "shareMode": false
                });
            }
        }

        IconButton {
            iconName: "share"
            text: i18n.tr("Share")
            onClicked: {
                videoViewer.pause();
                pageStack.push(Qt.resolvedUrl("components/ContentTransferPage.qml"), {
                    "transferUrl": previewPage.videoPath,
                    "transferContentType": ContentType.Videos,
                    "shareMode": true
                });
            }
        }

    }

    header: PageHeader {
        id: previewHeader

        title: videoPath.split("/").pop() || i18n.tr("Video")
        leadingActionBar.actions: [
            Action {
                iconName: "back"
                text: i18n.tr("Back")
                onTriggered: {
                    videoViewer.resetPlayback();
                    pageStack.pop();
                }
            }
        ]
    }

}
