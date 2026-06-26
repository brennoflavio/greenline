import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import QtQuick 2.7

Dialog {
    id: root

    property bool opening: false
    property string phoneError: i18n.tr("Enter digits only, no leading zero (e.g. 5511999999999)")
    property bool phoneValid: /^[1-9][0-9]{6,14}$/.test(phoneInput.text)

    signal chatRequested(string phoneNumber)

    title: i18n.tr("New Chat")
    text: i18n.tr("Enter a phone number with country code, digits only (e.g. 5511999999999).")

    TextField {
        id: phoneInput

        placeholderText: "5511999999999"
        inputMethodHints: Qt.ImhDigitsOnly
        Component.onCompleted: forceActiveFocus()
    }

    Label {
        visible: phoneInput.text.length > 0 && !root.phoneValid
        text: root.phoneError
        fontSize: "x-small"
        color: theme.palette.normal.negative
        wrapMode: Text.WordWrap
    }

    Button {
        text: i18n.tr("Cancel")
        enabled: !root.opening
        onClicked: PopupUtils.close(root)
    }

    Button {
        text: i18n.tr("OK")
        color: theme.palette.normal.positive
        enabled: root.phoneValid && !root.opening
        onClicked: {
            Qt.inputMethod.commit();
            root.opening = true;
            root.chatRequested(phoneInput.text);
        }
    }

}
