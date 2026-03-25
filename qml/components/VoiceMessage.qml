import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3

MessageBubble {
    id: root

    property string duration: "0:00"
    property bool playing: false

    RowLayout {
        width: parent.width
        spacing: units.gu(1)

        Icon {
            name: root.playing ? "media-playback-pause" : "media-playback-start"
            width: units.gu(3)
            height: units.gu(3)
            color: LomiriColors.green
            Layout.alignment: Qt.AlignVCenter

            MouseArea {
                anchors.fill: parent
                onClicked: root.playing = !root.playing
            }

        }

        Rectangle {
            Layout.fillWidth: true
            height: units.gu(0.4)
            radius: height / 2
            color: "#c0c0c0"
            Layout.alignment: Qt.AlignVCenter

            Rectangle {
                width: parent.width * 0.35
                height: parent.height
                radius: height / 2
                color: LomiriColors.green
            }

            Rectangle {
                x: parent.width * 0.35 - width / 2
                y: -height / 4
                width: units.gu(1.2)
                height: units.gu(1.2)
                radius: width / 2
                color: LomiriColors.green
                anchors.verticalCenter: parent.verticalCenter
            }

        }

        Label {
            text: root.duration
            fontSize: "x-small"
            color: "#999999"
            Layout.alignment: Qt.AlignVCenter
        }

    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
