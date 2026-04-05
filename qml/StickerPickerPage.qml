import Lomiri.Components 1.3
import QtQuick 2.7
import io.thp.pyotherside 1.4

Page {
    id: stickerPickerPage

    property var stickers: []

    signal stickerSelected(string filePath)

    GridView {
        id: stickerGrid

        visible: stickers.length > 0
        cellWidth: parent.width / 4
        cellHeight: cellWidth
        model: stickers

        anchors {
            top: stickerHeader.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            margins: units.gu(1)
        }

        delegate: Item {
            width: stickerGrid.cellWidth
            height: stickerGrid.cellHeight

            Image {
                anchors.fill: parent
                anchors.margins: units.gu(0.5)
                source: modelData
                fillMode: Image.PreserveAspectFit

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        pageStack.pop();
                        stickerPickerPage.stickerSelected(modelData);
                    }
                }

            }

        }

    }

    Label {
        visible: stickers.length === 0 && !python.loading
        text: i18n.tr("No stickers yet.\nReceive stickers in chats to use them here.")
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        color: theme.palette.normal.backgroundSecondaryText
        anchors.centerIn: parent
        width: parent.width - units.gu(4)
    }

    Python {
        id: python

        property bool loading: true

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                call('main.get_cached_stickers', [], function(result) {
                    loading = false;
                    if (result.success)
                        stickers = result.stickers;

                });
            });
        }
    }

    header: PageHeader {
        id: stickerHeader

        title: i18n.tr("Send Sticker")
        leadingActionBar.actions: [
            Action {
                iconName: "back"
                onTriggered: pageStack.pop()
            }
        ]
    }

}
