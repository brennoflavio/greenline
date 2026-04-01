import Lomiri.Components 1.3
import Lomiri.Content 1.3
import QtMultimedia 5.9
import QtQuick 2.7
import QtQuick.Layouts 1.3
import "ut_components"

Page {
    id: previewPage

    property string videoPath: ""

    function formatTime(ms) {
        if (!ms || ms < 0)
            return "0:00";

        var secs = Math.floor(ms / 1000);
        var mins = Math.floor(secs / 60);
        secs = secs % 60;
        return mins + ":" + (secs < 10 ? "0" : "") + secs;
    }

    Video {
        id: videoPlayer

        source: previewPage.videoPath || ""
        fillMode: VideoOutput.PreserveAspectFit
        autoPlay: false
        onStatusChanged: {
            if (status === MediaPlayer.EndOfMedia) {
                videoPlayer.seek(0);
                videoPlayer.pause();
            }
        }

        anchors {
            top: previewHeader.bottom
            left: parent.left
            right: parent.right
            bottom: controlsBar.top
        }

        MouseArea {
            anchors.fill: parent
            onClicked: {
                if (videoPlayer.playbackState === MediaPlayer.PlayingState)
                    videoPlayer.pause();
                else
                    videoPlayer.play();
            }
        }

        Rectangle {
            anchors.centerIn: parent
            width: units.gu(6)
            height: units.gu(6)
            radius: width / 2
            color: "#80000000"
            visible: videoPlayer.playbackState !== MediaPlayer.PlayingState

            Icon {
                anchors.centerIn: parent
                name: "media-playback-start"
                width: units.gu(4)
                height: units.gu(4)
                color: "white"
            }

        }

    }

    Rectangle {
        id: controlsBar

        height: units.gu(5)
        color: theme.palette.normal.background

        anchors {
            left: parent.left
            right: parent.right
            bottom: bottomBar.top
        }

        RowLayout {
            spacing: units.gu(1)

            anchors {
                fill: parent
                leftMargin: units.gu(1.5)
                rightMargin: units.gu(1.5)
            }

            Icon {
                name: videoPlayer.playbackState === MediaPlayer.PlayingState ? "media-playback-pause" : "media-playback-start"
                width: units.gu(3)
                height: units.gu(3)
                color: theme.palette.normal.foregroundText
                Layout.alignment: Qt.AlignVCenter

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        if (videoPlayer.playbackState === MediaPlayer.PlayingState)
                            videoPlayer.pause();
                        else
                            videoPlayer.play();
                    }
                }

            }

            Label {
                text: formatTime(videoPlayer.position)
                fontSize: "x-small"
                Layout.alignment: Qt.AlignVCenter
            }

            Rectangle {
                id: progressBar

                readonly property real progress: videoPlayer.duration > 0 ? Math.max(0, Math.min(1, videoPlayer.position / videoPlayer.duration)) : 0

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
                }

                MouseArea {
                    anchors.fill: parent
                    anchors.topMargin: -units.gu(1)
                    anchors.bottomMargin: -units.gu(1)
                    onClicked: {
                        if (videoPlayer.duration > 0)
                            videoPlayer.seek(mouseX / width * videoPlayer.duration);

                    }
                }

            }

            Label {
                text: formatTime(videoPlayer.duration)
                fontSize: "x-small"
                Layout.alignment: Qt.AlignVCenter
            }

        }

    }

    BottomBar {
        id: bottomBar

        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
        }

        IconButton {
            iconName: "save"
            text: i18n.tr("Save")
            onClicked: {
                videoPlayer.pause();
                pageStack.push(savePage, {
                    "videoUrl": previewPage.videoPath
                });
            }
        }

        IconButton {
            iconName: "share"
            text: i18n.tr("Share")
            onClicked: {
                videoPlayer.pause();
                pageStack.push(sharePage, {
                    "videoUrl": previewPage.videoPath
                });
            }
        }

    }

    Component {
        id: savePage

        Page {
            id: savePageInstance

            property string videoUrl: ""
            property var activeTransfer

            ContentPeerPicker {
                contentType: ContentType.Videos
                handler: ContentHandler.Destination
                onPeerSelected: {
                    savePageInstance.activeTransfer = peer.request();
                    if (savePageInstance.activeTransfer) {
                        savePageInstance.activeTransfer.items = [saveContentItem];
                        savePageInstance.activeTransfer.state = ContentTransfer.Charged;
                        pageStack.pop();
                    }
                }
                onCancelPressed: {
                    if (savePageInstance.activeTransfer)
                        savePageInstance.activeTransfer.state = ContentTransfer.Aborted;

                    pageStack.pop();
                }

                anchors {
                    top: saveHeader.bottom
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }

            }

            ContentItem {
                id: saveContentItem

                url: savePageInstance.videoUrl
            }

            header: PageHeader {
                id: saveHeader

                title: i18n.tr("Save to")
                leadingActionBar.actions: [
                    Action {
                        iconName: "back"
                        onTriggered: {
                            if (savePageInstance.activeTransfer)
                                savePageInstance.activeTransfer.state = ContentTransfer.Aborted;

                            pageStack.pop();
                        }
                    }
                ]
            }

        }

    }

    Component {
        id: sharePage

        Page {
            id: sharePageInstance

            property string videoUrl: ""
            property var activeTransfer

            ContentPeerPicker {
                contentType: ContentType.Videos
                handler: ContentHandler.Share
                onPeerSelected: {
                    sharePageInstance.activeTransfer = peer.request();
                    if (sharePageInstance.activeTransfer) {
                        sharePageInstance.activeTransfer.items = [shareContentItem];
                        sharePageInstance.activeTransfer.state = ContentTransfer.Charged;
                        pageStack.pop();
                    }
                }
                onCancelPressed: {
                    if (sharePageInstance.activeTransfer)
                        sharePageInstance.activeTransfer.state = ContentTransfer.Aborted;

                    pageStack.pop();
                }

                anchors {
                    top: shareHeader.bottom
                    left: parent.left
                    right: parent.right
                    bottom: parent.bottom
                }

            }

            ContentItem {
                id: shareContentItem

                url: sharePageInstance.videoUrl
            }

            header: PageHeader {
                id: shareHeader

                title: i18n.tr("Share")
                leadingActionBar.actions: [
                    Action {
                        iconName: "back"
                        onTriggered: {
                            if (sharePageInstance.activeTransfer)
                                sharePageInstance.activeTransfer.state = ContentTransfer.Aborted;

                            pageStack.pop();
                        }
                    }
                ]
            }

        }

    }

    header: PageHeader {
        id: previewHeader

        title: videoPath.split("/").pop() || i18n.tr("Video")
        leadingActionBar.actions: [
            Action {
                iconName: "back"
                text: i18n.tr("Back")
                onTriggered: {
                    videoPlayer.stop();
                    pageStack.pop();
                }
            }
        ]
    }

}
