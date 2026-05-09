import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import QtQuick 2.7
import qml.AudioCapture 1.0 as AudioCapture

Dialog {
    id: root

    property bool awaitingCancelCleanup: false
    property bool submitted: false

    signal recordingAccepted(string filePath, int durationSeconds)

    function formatDuration(durationMs) {
        var totalSeconds = Math.floor(durationMs / 1000);
        var minutes = Math.floor(totalSeconds / 60);
        var seconds = totalSeconds % 60;
        return minutes + ":" + (seconds < 10 ? "0" : "") + seconds;
    }

    function cancelDialog() {
        if (recorder.recording || recorder.status === "finalizing") {
            awaitingCancelCleanup = true;
            recorder.clearOutput();
            return ;
        }
        recorder.clearOutput();
        PopupUtils.close(root);
    }

    title: i18n.tr("Record Voice Message")

    AudioCapture.AudioCaptureRecorder {
        id: recorder
    }

    Connections {
        target: recorder
        onOutputFileChanged: {
            if (root.awaitingCancelCleanup && !recorder.recording && recorder.status !== "finalizing") {
                root.awaitingCancelCleanup = false;
                PopupUtils.close(root);
            }
        }
    }

    Label {
        text: recorder.recording ? i18n.tr("Recording…") : (recorder.readyToSend ? i18n.tr("Recording ready to send") : i18n.tr("Tap record to capture a voice message"))
        wrapMode: Text.WordWrap
    }

    Label {
        text: i18n.tr("Duration: %1").arg(root.formatDuration(recorder.duration))
    }

    Label {
        text: i18n.tr("Status: %1").arg(recorder.readyToSend ? i18n.tr("ready") : recorder.status)
        color: theme.palette.normal.backgroundTertiaryText
    }

    Label {
        visible: recorder.errorString !== ""
        text: i18n.tr("Error: %1").arg(recorder.errorString)
        wrapMode: Text.WordWrap
        color: theme.palette.normal.negative
    }

    Button {
        text: recorder.recording ? i18n.tr("Stop") : (recorder.readyToSend ? i18n.tr("Record Again") : i18n.tr("Record"))
        enabled: !root.awaitingCancelCleanup && recorder.status !== "starting" && recorder.status !== "finalizing"
        color: recorder.recording ? theme.palette.normal.negative : theme.palette.normal.positive
        onClicked: {
            if (recorder.recording) {
                recorder.stop();
                return ;
            }
            if (recorder.readyToSend)
                recorder.clearOutput();

            recorder.start();
        }
    }

    Button {
        text: i18n.tr("Cancel")
        enabled: !root.awaitingCancelCleanup
        color: theme.palette.normal.base
        onClicked: root.cancelDialog()
    }

    Button {
        text: i18n.tr("Send")
        enabled: recorder.readyToSend && !root.awaitingCancelCleanup && !root.submitted
        color: theme.palette.normal.positive
        onClicked: {
            if (root.submitted)
                return ;

            root.submitted = true;
            root.recordingAccepted(recorder.outputFile, Math.max(1, Math.ceil(recorder.duration / 1000)));
            PopupUtils.close(root);
        }
    }

}
