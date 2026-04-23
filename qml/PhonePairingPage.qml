import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3
import io.thp.pyotherside 1.4
import "ut_components"

Page {
    id: phonePairingPage

    property string pairingState: "input"
    property string pairingCode: ""
    property string phoneError: ""

    Flickable {
        contentHeight: content.height + units.gu(4)
        clip: true

        anchors {
            top: phonePairingPage.header.bottom
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

            Column {
                id: inputView

                width: parent.width
                spacing: units.gu(3)
                visible: pairingState === "input"

                Label {
                    width: parent.width
                    text: i18n.tr("Enter your phone number with country code, digits only (e.g. 5511999999999).")
                    fontSize: "small"
                    color: theme.palette.normal.backgroundTertiaryText
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }

                InputField {
                    id: phoneInput

                    width: parent.width
                    title: i18n.tr("Phone Number")
                    placeholder: "5511999999999"
                    validationRegex: "^[1-9][0-9]{6,14}$"
                    errorMessage: i18n.tr("Enter digits only, no leading zero (e.g. 5511999999999)")
                    required: true
                }

                Label {
                    width: parent.width
                    text: phoneError
                    fontSize: "small"
                    color: theme.palette.normal.negative
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    visible: phoneError !== ""
                }

                ActionButton {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: i18n.tr("Get Pairing Code")
                    iconName: "lock"
                    enabled: phoneInput.isValid
                    onClicked: {
                        phoneError = "";
                        pairingState = "loading";
                        python.call('main.pair_phone', [phoneInput.text], function(result) {
                            if (result.success) {
                                pairingCode = result.code;
                                pairingState = "code";
                            } else {
                                phoneError = result.message || i18n.tr("Failed to get pairing code");
                                pairingState = "input";
                            }
                        });
                    }
                }

            }

            Column {
                id: loadingView

                width: parent.width
                spacing: units.gu(3)
                visible: pairingState === "loading"

                LoadingSpinner {
                    anchors.horizontalCenter: parent.horizontalCenter
                    running: pairingState === "loading"
                }

                Label {
                    width: parent.width
                    text: i18n.tr("Requesting pairing code...")
                    fontSize: "small"
                    color: theme.palette.normal.backgroundTertiaryText
                    horizontalAlignment: Text.AlignHCenter
                }

                Label {
                    width: parent.width
                    text: "<a href='#'>" + i18n.tr("Cancel") + "</a>"
                    fontSize: "small"
                    horizontalAlignment: Text.AlignHCenter
                    linkColor: theme.palette.normal.activity
                    onLinkActivated: pairingState = "input"
                }

            }

            Column {
                id: codeView

                width: parent.width
                spacing: units.gu(3)
                visible: pairingState === "code"

                Label {
                    width: parent.width
                    text: i18n.tr("Open WhatsApp on your phone, go to Settings → Linked Devices → Link with phone number, then enter the code below.")
                    fontSize: "small"
                    color: theme.palette.normal.backgroundTertiaryText
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }

                Label {
                    width: parent.width
                    text: pairingCode
                    fontSize: "x-large"
                    font.bold: true
                    font.letterSpacing: units.gu(0.5)
                    horizontalAlignment: Text.AlignHCenter
                    color: theme.palette.normal.activity
                }

                LoadingSpinner {
                    anchors.horizontalCenter: parent.horizontalCenter
                    running: pairingState === "code"
                }

                Label {
                    width: parent.width
                    text: i18n.tr("Waiting for confirmation...")
                    fontSize: "small"
                    color: theme.palette.normal.backgroundTertiaryText
                    horizontalAlignment: Text.AlignHCenter
                }

            }

            KeyboardSpacer {
            }

        }

    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                setHandler('session-status', function(status) {
                    if (status.logged_in) {
                        isAuthenticating = false;
                        isLoggedIn = true;
                        pageStack.clear();
                        pageStack.push(Qt.resolvedUrl("ChatListPage.qml"));
                    }
                });
            });
        }
    }

    header: AppHeader {
        pageTitle: i18n.tr("Login with Phone Number")
        isRootPage: false
        showSettingsButton: true
        onSettingsClicked: pageStack.push(Qt.resolvedUrl("SettingsPage.qml"))
    }

}
