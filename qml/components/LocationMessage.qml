import "../ut_components"
import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3

MessageBubble {
    id: root

    property string title: ""
    property string detail: ""
    property string linkUrl: ""
    readonly property string displayTitle: title || detail || "📍 Location"

    copyableText: title || detail || linkUrl

    Item {
        width: parent.width
        height: locationRow.height

        RowLayout {
            id: locationRow

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
                    name: "location"
                    width: units.gu(3)
                    height: units.gu(3)
                    color: root.linkUrl ? LomiriColors.green : theme.palette.normal.backgroundSecondaryText
                }

            }

            Column {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: units.gu(0.2)

                Label {
                    text: root.displayTitle
                    fontSize: "small"
                    color: "#303030"
                    wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                    width: parent.width
                }

                Label {
                    text: root.linkUrl ? i18n.tr("Tap to open") : i18n.tr("Unavailable")
                    fontSize: "x-small"
                    color: "#999999"
                }

            }

        }

        MouseArea {
            anchors.fill: parent
            enabled: !!root.linkUrl
            onClicked: Qt.openUrlExternally(root.linkUrl)
        }

    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
