import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3

Dialog {
    id: root

    signal photoRequested()
    signal videoRequested()
    signal audioRequested()
    signal documentRequested()
    signal stickerRequested()
    signal contactRequested()
    signal locationRequested()

    title: i18n.tr("Send Attachment")

    Button {
        text: i18n.tr("Photo")
        onClicked: {
            PopupUtils.close(root);
            root.photoRequested();
        }
    }

    Button {
        text: i18n.tr("Video")
        onClicked: {
            PopupUtils.close(root);
            root.videoRequested();
        }
    }

    Button {
        text: i18n.tr("Audio")
        onClicked: {
            PopupUtils.close(root);
            root.audioRequested();
        }
    }

    Button {
        text: i18n.tr("Document")
        onClicked: {
            PopupUtils.close(root);
            root.documentRequested();
        }
    }

    Button {
        text: i18n.tr("Sticker")
        onClicked: {
            PopupUtils.close(root);
            root.stickerRequested();
        }
    }

    Button {
        text: i18n.tr("Contact")
        onClicked: {
            PopupUtils.close(root);
            root.contactRequested();
        }
    }

    Button {
        text: i18n.tr("Location")
        onClicked: {
            PopupUtils.close(root);
            root.locationRequested();
        }
    }

    Button {
        text: i18n.tr("Cancel")
        color: theme.palette.normal.base
        onClicked: PopupUtils.close(root)
    }

}
