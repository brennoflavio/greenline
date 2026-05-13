import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7

Item {
    id: root

    property string readReceipt: ""
    property string sendStatus: ""
    property color inactiveColor: "#999999"
    property color activeColor: LomiriColors.lightBlue
    property bool indicatorVisible: true

    visible: indicatorVisible && (sendStatus === "pending" || readReceipt === "sent" || readReceipt === "delivered" || readReceipt === "read")

    Icon {
        anchors.fill: parent
        name: "emoji-recent-symbolic"
        color: root.inactiveColor
        visible: root.sendStatus === "pending"
    }

    Icon {
        anchors.fill: parent
        name: "ok"
        color: root.inactiveColor
        visible: root.sendStatus !== "pending" && root.readReceipt === "sent"
    }

    Image {
        id: doubleCheckIcon

        anchors.fill: parent
        source: Qt.resolvedUrl("../assets/message-status-double-check.svg")
        sourceSize.width: width
        sourceSize.height: height
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        visible: false
    }

    ColorOverlay {
        anchors.fill: doubleCheckIcon
        source: doubleCheckIcon
        color: root.readReceipt === "read" ? root.activeColor : root.inactiveColor
        visible: root.sendStatus !== "pending" && (root.readReceipt === "delivered" || root.readReceipt === "read")
    }

}
