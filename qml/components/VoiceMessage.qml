import "../ut_components"
import Lomiri.Components 1.3
import QtMultimedia 5.9
import QtQuick 2.7
import QtQuick.Layouts 1.3

MessageBubble {
    id: root

    property string duration: "0:00"
    property string mediaPath: ""
    property bool playing: false
    property bool downloading: false

    signal downloadRequested()

    Item {
        width: 0
        height: 0

        Audio {
            id: audioPlayer

            source: root.mediaPath
            onStatusChanged: {
                if (status === Audio.EndOfMedia) {
                    root.playing = false;
                    audioPlayer.seek(0);
                }
            }
        }

    }

    RowLayout {
        width: parent.width
        spacing: units.gu(1)

        Icon {
            name: {
                if (root.downloading)
                    return "sync-updating";

                if (!root.mediaPath)
                    return "save";

                return root.playing ? "media-playback-pause" : "media-playback-start";
            }
            width: units.gu(3)
            height: units.gu(3)
            color: LomiriColors.green
            Layout.alignment: Qt.AlignVCenter

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    if (!root.mediaPath && !root.downloading) {
                        root.downloadRequested();
                        return ;
                    }
                    if (root.mediaPath) {
                        if (root.playing) {
                            audioPlayer.pause();
                            root.playing = false;
                        } else {
                            audioPlayer.play();
                            root.playing = true;
                        }
                    }
                }
            }

        }

        Rectangle {
            id: progressBar

            property real progress: audioPlayer.duration > 0 ? audioPlayer.position / audioPlayer.duration : 0

            Layout.fillWidth: true
            height: units.gu(0.4)
            radius: height / 2
            color: "#c0c0c0"
            Layout.alignment: Qt.AlignVCenter

            Rectangle {
                width: parent.width * progressBar.progress
                height: parent.height
                radius: height / 2
                color: LomiriColors.green
            }

            Rectangle {
                x: parent.width * progressBar.progress - width / 2
                width: units.gu(1.2)
                height: units.gu(1.2)
                radius: width / 2
                color: LomiriColors.green
                anchors.verticalCenter: parent.verticalCenter
                visible: root.mediaPath !== ""
            }

            MouseArea {
                anchors.fill: parent
                anchors.topMargin: -units.gu(1)
                anchors.bottomMargin: -units.gu(1)
                onClicked: {
                    if (audioPlayer.duration > 0) {
                        var ratio = mouseX / width;
                        audioPlayer.seek(ratio * audioPlayer.duration);
                    }
                }
            }

        }

        Label {
            Layout.preferredWidth: units.gu(4)
            horizontalAlignment: Text.AlignRight
            text: {
                if (root.playing && audioPlayer.duration > 0) {
                    var secs = Math.floor(audioPlayer.position / 1000);
                    var mins = Math.floor(secs / 60);
                    secs = secs % 60;
                    return mins + ":" + (secs < 10 ? "0" : "") + secs;
                }
                return root.duration;
            }
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
