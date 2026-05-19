import Lomiri.Components 1.3
import Lomiri.Content 1.3
import QtQuick 2.7

Page {
    id: transferPage

    property string transferUrl: ""
    property int transferContentType: ContentType.All
    property bool shareMode: false
    property string pageTitle: shareMode ? i18n.tr("Share") : i18n.tr("Save to")
    property var activeTransfer

    function abortTransfer() {
        if (activeTransfer)
            activeTransfer.state = ContentTransfer.Aborted;

    }

    ContentPeerPicker {
        contentType: transferPage.transferContentType
        handler: transferPage.shareMode ? ContentHandler.Share : ContentHandler.Destination
        onPeerSelected: {
            transferPage.activeTransfer = peer.request();
            if (transferPage.activeTransfer) {
                transferPage.activeTransfer.items = [transferContentItem];
                transferPage.activeTransfer.state = ContentTransfer.Charged;
                pageStack.pop();
            }
        }
        onCancelPressed: {
            transferPage.abortTransfer();
            pageStack.pop();
        }

        anchors {
            top: transferHeader.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

    }

    ContentItem {
        id: transferContentItem

        url: transferPage.transferUrl
    }

    header: PageHeader {
        id: transferHeader

        title: transferPage.pageTitle
        leadingActionBar.actions: [
            Action {
                iconName: "back"
                onTriggered: {
                    transferPage.abortTransfer();
                    pageStack.pop();
                }
            }
        ]
    }

}
