import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: settingsPage

    function resetApp() {
        loadToast.showing = true;
        python.call('main.clear_data', [], function(result) {
            loadToast.showing = false;
            if (result.success) {
                pageStack.clear();
                pageStack.push(Qt.resolvedUrl("DaemonSetupPage.qml"));
            }
        });
    }

    Flickable {
        contentHeight: content.height + units.gu(4)
        clip: true

        anchors {
            top: settingsPage.header.bottom
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        Column {
            id: content

            width: parent.width
            spacing: units.gu(2)
            topPadding: units.gu(1)

            ConfigurationGroup {
                title: i18n.tr("Data")

                Item {
                    width: parent.width
                    height: units.gu(6)

                    RowLayout {
                        anchors {
                            fill: parent
                            leftMargin: units.gu(2)
                            rightMargin: units.gu(2)
                        }

                        Label {
                            text: i18n.tr("Uninstall the daemon, log out from WhatsApp, and delete all local data including messages, settings and cache.")
                            fontSize: "small"
                            color: theme.palette.normal.backgroundTertiaryText
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                    }

                }

            }

            ActionButton {
                anchors.horizontalCenter: parent.horizontalCenter
                text: i18n.tr("Reset App")
                iconName: "reset"
                backgroundColor: theme.palette.normal.negative
                onClicked: {
                    PopupUtils.open(confirmResetDialog);
                }
            }

        }

    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
            });
        }
    }

    Component {
        id: confirmResetDialog

        Dialog {
            id: dialog

            title: i18n.tr("Reset App")
            text: i18n.tr("This will uninstall the daemon, log out from WhatsApp, and delete all local data. You will need to reinstall the daemon and scan the QR code again to reconnect.")

            Button {
                text: i18n.tr("Cancel")
                onClicked: PopupUtils.close(dialog)
            }

            Button {
                text: i18n.tr("Reset App")
                color: theme.palette.normal.negative
                onClicked: {
                    PopupUtils.close(dialog);
                    settingsPage.resetApp();
                }
            }

        }

    }

    LoadToast {
        id: loadToast

        showing: false
        message: i18n.tr("Resetting app...")
    }

    header: AppHeader {
        pageTitle: i18n.tr("Settings")
        isRootPage: false
    }

}
