import Lomiri.Components 1.3
import Lomiri.Components.Popups 1.3
import QtPositioning 5.12
import QtQuick 2.7

Dialog {
    id: root

    property bool completed: false

    signal locationSelected(double latitude, double longitude)
    signal fetchFailed(string message)

    function cleanup() {
        timeoutTimer.stop();
        positionSource.stop();
    }

    function finishSuccess(latitude, longitude) {
        if (completed)
            return ;

        completed = true;
        cleanup();
        PopupUtils.close(root);
        root.locationSelected(latitude, longitude);
    }

    function finishFailure(message) {
        if (completed)
            return ;

        completed = true;
        cleanup();
        PopupUtils.close(root);
        root.fetchFailed(message);
    }

    function cancelFetch() {
        if (completed)
            return ;

        completed = true;
        cleanup();
        PopupUtils.close(root);
    }

    function startFetch() {
        if (completed)
            return ;

        if (!positionSource.valid) {
            finishFailure(i18n.tr("Location services are unavailable"));
            return ;
        }
        timeoutTimer.start();
        positionSource.start();
    }

    title: i18n.tr("Share Current Location")
    text: i18n.tr("Fetching your current location…")
    Component.onCompleted: startFetch()

    PositionSource {
        id: positionSource

        preferredPositioningMethods: PositionSource.AllPositioningMethods
        active: false
        onPositionChanged: {
            if (root.completed || !position || !position.coordinate || !position.coordinate.isValid)
                return ;

            root.finishSuccess(position.coordinate.latitude, position.coordinate.longitude);
        }
        onSourceErrorChanged: {
            if (!root.completed && sourceError !== PositionSource.NoError)
                root.finishFailure(i18n.tr("Unable to get current location"));

        }
    }

    Timer {
        id: timeoutTimer

        interval: 60000
        repeat: false
        onTriggered: root.finishFailure(i18n.tr("Location request timed out"))
    }

    Button {
        text: i18n.tr("Cancel")
        color: theme.palette.normal.base
        onClicked: root.cancelFetch()
    }

}
