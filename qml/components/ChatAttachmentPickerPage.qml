import Lomiri.Components 1.3
import Lomiri.Content 1.3
import QtQuick 2.7

Page {
    id: root

    property string pickerTitle: ""
    property int pickerContentType: ContentType.Pictures
    property var activeTransfer: null

    signal fileSelected(string filePath)

    ContentStore {
        id: contentStore

        scope: ContentScope.App
    }

    ContentPeerPicker {
        contentType: root.pickerContentType
        handler: ContentHandler.Source
        onPeerSelected: {
            root.activeTransfer = peer.request(contentStore);
            root.activeTransfer.selectionType = ContentTransfer.Single;
        }
        onCancelPressed: {
            if (root.activeTransfer)
                root.activeTransfer.state = ContentTransfer.Aborted;

            pageStack.pop();
        }

        anchors {
            top: pickerHeader.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

    }

    Connections {
        function onStateChanged() {
            if (root.activeTransfer.state === ContentTransfer.Charged) {
                if (root.activeTransfer.items.length > 0) {
                    var fileUrl = root.activeTransfer.items[0].url.toString();
                    var filePath = fileUrl.replace("file://", "");
                    pageStack.pop();
                    root.fileSelected(filePath);
                }
            }
        }

        target: root.activeTransfer
        enabled: !!root.activeTransfer
        ignoreUnknownSignals: true
    }

    header: PageHeader {
        id: pickerHeader

        title: root.pickerTitle
        leadingActionBar.actions: [
            Action {
                iconName: "back"
                onTriggered: {
                    if (root.activeTransfer)
                        root.activeTransfer.state = ContentTransfer.Aborted;

                    pageStack.pop();
                }
            }
        ]
    }

}
