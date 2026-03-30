import Lomiri.Components 1.3
import Lomiri.Content 1.3
import QtQuick 2.7
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: previewPage

    property string imagePath: ""

    Image {
        source: previewPage.imagePath || ""
        fillMode: Image.PreserveAspectFit
        asynchronous: true

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
                pageStack.push(savePage, {
                    "imageUrl": previewPage.imagePath
                });
            }
        }

        IconButton {
            iconName: "share"
            text: i18n.tr("Share")
            onClicked: {
                pageStack.push(sharePage, {
                    "imageUrl": previewPage.imagePath
                });
            }
        }

    }

    Component {
        id: savePage

        Page {
            id: savePageInstance

            property string imageUrl: ""
            property var activeTransfer

            ContentPeerPicker {
                contentType: ContentType.Pictures
                handler: ContentHandler.Destination
                onPeerSelected: {
                    savePageInstance.activeTransfer = peer.request();
                    if (savePageInstance.activeTransfer) {
                        savePageInstance.activeTransfer.items = [saveContentItem];
                        savePageInstance.activeTransfer.state = ContentTransfer.Charged;
                        pageStack.pop();
                    }
                }
                onCancelPressed: {
                    if (savePageInstance.activeTransfer)
                        savePageInstance.activeTransfer.state = ContentTransfer.Aborted;

                    pageStack.pop();
                }

                anchors {
                    top: saveHeader.bottom
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }

            }

            ContentItem {
                id: saveContentItem

                url: savePageInstance.imageUrl
            }

            header: PageHeader {
                id: saveHeader

                title: i18n.tr("Save to")
                leadingActionBar.actions: [
                    Action {
                        iconName: "back"
                        onTriggered: {
                            if (savePageInstance.activeTransfer)
                                savePageInstance.activeTransfer.state = ContentTransfer.Aborted;

                            pageStack.pop();
                        }
                    }
                ]
            }

        }

    }

    Component {
        id: sharePage

        Page {
            id: sharePageInstance

            property string imageUrl: ""
            property var activeTransfer

            ContentPeerPicker {
                contentType: ContentType.Pictures
                handler: ContentHandler.Share
                onPeerSelected: {
                    sharePageInstance.activeTransfer = peer.request();
                    if (sharePageInstance.activeTransfer) {
                        sharePageInstance.activeTransfer.items = [shareContentItem];
                        sharePageInstance.activeTransfer.state = ContentTransfer.Charged;
                        pageStack.pop();
                    }
                }
                onCancelPressed: {
                    if (sharePageInstance.activeTransfer)
                        sharePageInstance.activeTransfer.state = ContentTransfer.Aborted;

                    pageStack.pop();
                }

                anchors {
                    top: shareHeader.bottom
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }

            }

            ContentItem {
                id: shareContentItem

                url: sharePageInstance.imageUrl
            }

            header: PageHeader {
                id: shareHeader

                title: i18n.tr("Share")
                leadingActionBar.actions: [
                    Action {
                        iconName: "back"
                        onTriggered: {
                            if (sharePageInstance.activeTransfer)
                                sharePageInstance.activeTransfer.state = ContentTransfer.Aborted;

                            pageStack.pop();
                        }
                    }
                ]
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
