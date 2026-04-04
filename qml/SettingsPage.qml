import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: settingsPage

    property bool daemonInstalled: false
    property bool daemonActive: false
    property bool checkingDaemon: true

    function clearData() {
        python.call('main.clear_data', [], function(result) {
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
                title: i18n.tr("Daemon")

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
                            text: i18n.tr("Status")
                            fontSize: "medium"
                            Layout.fillWidth: true
                        }

                        LoadingSpinner {
                            running: checkingDaemon
                            visible: checkingDaemon
                            Layout.alignment: Qt.AlignRight
                        }

                        Label {
                            visible: !checkingDaemon
                            text: daemonActive ? i18n.tr("Running") : (daemonInstalled ? i18n.tr("Stopped") : i18n.tr("Not installed"))
                            fontSize: "medium"
                            color: daemonActive ? LomiriColors.green : LomiriColors.red
                            Layout.alignment: Qt.AlignRight
                        }

                    }

                }

            }

            ActionButton {
                anchors.horizontalCenter: parent.horizontalCenter
                text: daemonInstalled ? i18n.tr("Uninstall Daemon") : i18n.tr("Install Daemon")
                iconName: daemonInstalled ? "delete" : "import"
                backgroundColor: daemonInstalled ? theme.palette.normal.negative : theme.palette.normal.positive
                enabled: !checkingDaemon
                onClicked: {
                    checkingDaemon = true;
                    if (daemonInstalled) {
                        python.call('main.uninstall_daemon', [], function(result) {
                            if (result.success) {
                                pageStack.clear();
                                pageStack.push(Qt.resolvedUrl("DaemonSetupPage.qml"));
                            } else {
                                checkingDaemon = false;
                            }
                        });
                    } else {
                        python.call('main.install_daemon', [], function(result) {
                            daemonInstalled = result.success;
                            daemonActive = result.success;
                            checkingDaemon = false;
                        });
                    }
                }
            }

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
                            text: i18n.tr("Clear all local data including messages and settings")
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
                text: i18n.tr("Clear Data")
                iconName: "reset"
                backgroundColor: theme.palette.normal.negative
                onClicked: {
                    PopupUtils.open(confirmClearDataDialog);
                }
            }

        }

    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                python.call('main.check_daemon_status', [], function(result) {
                    daemonInstalled = result.installed;
                    daemonActive = result.active;
                    checkingDaemon = false;
                });
            });
        }
    }

    Component {
        id: confirmClearDataDialog

        Dialog {
            id: dialog

            title: i18n.tr("Clear Data")
            text: i18n.tr("This will log out from WhatsApp and delete all local data including messages, settings and cache. You will need to scan the QR code again to reconnect.")

            Button {
                text: i18n.tr("Cancel")
                onClicked: PopupUtils.close(dialog)
            }

            Button {
                text: i18n.tr("Clear Data")
                color: theme.palette.normal.negative
                onClicked: {
                    PopupUtils.close(dialog);
                    settingsPage.clearData();
                }
            }

        }

    }

    header: AppHeader {
        pageTitle: i18n.tr("Settings")
        isRootPage: false
    }

}
