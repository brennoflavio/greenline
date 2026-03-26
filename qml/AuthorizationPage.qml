import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: authPage

    Flickable {
        contentHeight: content.height + units.gu(4)
        clip: true

        anchors {
            top: authPage.header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        Column {
            id: content

            spacing: units.gu(3)

            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
                topMargin: units.gu(3)
                leftMargin: units.gu(3)
                rightMargin: units.gu(3)
            }

            Label {
                width: parent.width
                text: i18n.tr("Scan QR Code")
                fontSize: "x-large"
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }

            Label {
                width: parent.width
                text: i18n.tr("Open WhatsApp on your phone, go to Settings → Linked Devices → Link a Device, then scan the code below.")
                fontSize: "small"
                color: theme.palette.normal.backgroundTertiaryText
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
            }

            Rectangle {
                width: units.gu(28)
                height: units.gu(28)
                anchors.horizontalCenter: parent.horizontalCenter
                color: "white"
                radius: units.gu(1)

                Image {
                    id: qrImage

                    fillMode: Image.PreserveAspectFit
                    source: ""
                    cache: false
                    visible: source != ""

                    anchors {
                        fill: parent
                        margins: units.gu(2)
                    }

                }

                Column {
                    anchors.centerIn: parent
                    spacing: units.gu(1)
                    visible: qrImage.source == ""

                    ActivityIndicator {
                        anchors.horizontalCenter: parent.horizontalCenter
                        running: true
                    }

                    Label {
                        text: i18n.tr("Loading QR Code...")
                        fontSize: "small"
                        color: theme.palette.normal.backgroundTertiaryText
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                }

            }

            Label {
                width: parent.width
                text: i18n.tr("The code refreshes automatically. Keep this screen open while scanning.")
                fontSize: "x-small"
                color: theme.palette.normal.backgroundTertiaryText
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
            }

        }

    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                isAuthenticating = true;
                setHandler('session-status', function(status) {
                    if (status.logged_in) {
                        isAuthenticating = false;
                        pageStack.clear();
                        pageStack.push(Qt.resolvedUrl("ChatListPage.qml"));
                    } else if (status.qr_image_path !== "") {
                        qrImage.source = status.qr_image_path;
                    }
                });
            });
        }
        Component.onDestruction: {
            isAuthenticating = false;
        }
    }

    header: AppHeader {
        pageTitle: i18n.tr("Link Device")
        isRootPage: true
        appIconName: "call-start"
    }

}
