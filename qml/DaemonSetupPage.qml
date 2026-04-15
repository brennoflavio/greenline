import Lomiri.Components 1.3
import QtQuick 2.7
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: daemonSetupPage

    property bool daemonInstalled: false
    property bool loading: false
    property string errorMessage: ""

    Column {
        anchors.centerIn: parent
        width: parent.width - units.gu(4)
        spacing: units.gu(3)

        Image {
            source: Qt.resolvedUrl("../assets/logo-no-bg.png")
            anchors.horizontalCenter: parent.horizontalCenter
            width: units.gu(16)
            height: units.gu(16)
            fillMode: Image.PreserveAspectFit
        }

        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Greenline"
            fontSize: "x-large"
            font.weight: Font.Medium
        }

        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: daemonInstalled ? i18n.tr("The background service is installed but not running.") : i18n.tr("The background service needs to be installed to sync your messages.")
            fontSize: "medium"
            color: theme.palette.normal.backgroundSecondaryText
            visible: !loading
        }

        Label {
            anchors.horizontalCenter: parent.horizontalCenter
            text: errorMessage
            fontSize: "small"
            color: LomiriColors.red
            wrapMode: Text.WordWrap
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            visible: errorMessage !== ""
        }

        ActionButton {
            anchors.horizontalCenter: parent.horizontalCenter
            text: daemonInstalled ? i18n.tr("Start Service") : i18n.tr("Install & Start")
            iconName: "media-playback-start"
            visible: !loading
            onClicked: {
                loading = true;
                errorMessage = "";
                python.call('main.install_daemon', [], function(result) {
                    if (result.success) {
                        python.call('main.check_daemon_version', [], function() {
                            python.call('main.get_session_status', [], function(session) {
                                python.call('main.start_event_loop', [], function() {
                                });
                                pageStack.clear();
                                if (session.logged_in) {
                                    isLoggedIn = true;
                                    pageStack.push(Qt.resolvedUrl("ChatListPage.qml"));
                                } else {
                                    pageStack.push(Qt.resolvedUrl("AuthorizationPage.qml"));
                                }
                            });
                        });
                    } else {
                        errorMessage = result.message;
                        loading = false;
                    }
                });
            }
        }

        LoadingSpinner {
            anchors.horizontalCenter: parent.horizontalCenter
            running: loading
            visible: loading
        }

    }

    LoadToast {
        id: loadToast

        showing: false
    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
            });
        }
    }

}
