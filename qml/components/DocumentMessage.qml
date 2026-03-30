import "../ut_components"
import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3

MessageBubble {
    id: root

    property string fileName: ""
    property string mediaPath: ""
    property bool downloading: false

    signal downloadRequested()

    RowLayout {
        width: parent.width
        spacing: units.gu(1)

        Rectangle {
            width: units.gu(5)
            height: units.gu(5)
            radius: units.gu(0.5)
            color: "#e8e8e8"
            Layout.alignment: Qt.AlignVCenter

            Icon {
                anchors.centerIn: parent
                name: root.mediaPath ? "document-open" : "save"
                width: units.gu(3)
                height: units.gu(3)
                color: root.mediaPath ? LomiriColors.green : theme.palette.normal.backgroundSecondaryText
            }

            LoadingSpinner {
                anchors.centerIn: parent
                running: root.downloading
                visible: root.downloading
            }

        }

        Column {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: units.gu(0.2)

            Label {
                text: root.fileName || i18n.tr("Document")
                fontSize: "small"
                color: "#303030"
                wrapMode: Text.WordWrap
                width: parent.width
            }

            Label {
                text: root.mediaPath ? i18n.tr("Downloaded") : i18n.tr("Tap to download")
                fontSize: "x-small"
                color: "#999999"
            }

        }

    }

    MouseArea {
        anchors.fill: parent
        onClicked: {
            if (!root.mediaPath && !root.downloading)
                root.downloadRequested();

        }
    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
