import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import QtQuick 2.7

Dialog {
    id: root

    property string messageId: ""
    property string initialText: ""
    property bool saving: false

    signal saveRequested(string messageId, string text)

    title: i18n.tr("Edit Message")

    TextArea {
        id: editMessageInput

        text: root.initialText
        autoSize: true
        maximumLineCount: 6
        Component.onCompleted: {
            forceActiveFocus();
            cursorPosition = text.length;
        }
    }

    Button {
        text: i18n.tr("Cancel")
        enabled: !root.saving
        onClicked: PopupUtils.close(root)
    }

    Button {
        text: i18n.tr("Save")
        color: theme.palette.normal.positive
        enabled: !root.saving
        onClicked: {
            Qt.inputMethod.commit();
            if (editMessageInput.text === root.initialText) {
                PopupUtils.close(root);
                return ;
            }
            root.saving = true;
            root.saveRequested(root.messageId, editMessageInput.text);
        }
    }

}
