import Lomiri.Components 1.3
import QtQuick 2.7
import QtQuick.Layouts 1.3

Item {
    id: bubble

    default property alias content: contentColumn.children
    property bool isOutgoing: false
    property string timestamp: ""
    property string readReceipt: ""

    width: parent.width
    height: wrapper.height + units.gu(0.5)

    Rectangle {
        id: wrapper

        width: Math.min(contentColumn.implicitWidth + units.gu(2), parent.width - units.gu(10))
        height: contentColumn.implicitHeight + units.gu(1)
        color: isOutgoing ? "#dcf8c6" : "#d4e6f9"
        radius: units.gu(1)

        anchors {
            right: isOutgoing ? parent.right : undefined
            left: isOutgoing ? undefined : parent.left
            rightMargin: isOutgoing ? units.gu(2) : units.gu(8)
            leftMargin: isOutgoing ? units.gu(8) : units.gu(2)
        }

        Column {
            id: contentColumn

            spacing: units.gu(0.3)

            anchors {
                fill: parent
                margins: units.gu(0.5)
            }

        }

        Row {
            spacing: units.gu(0.3)

            anchors {
                right: parent.right
                bottom: parent.bottom
                rightMargin: units.gu(0.5)
                bottomMargin: units.gu(0.3)
            }

            Label {
                text: bubble.timestamp
                fontSize: "xx-small"
                color: "#999999"
                anchors.verticalCenter: parent.verticalCenter
            }

            Icon {
                name: "tick"
                height: units.gu(1.4)
                width: units.gu(1.4)
                color: bubble.readReceipt === "read" ? LomiriColors.blue : "#999999"
                visible: bubble.isOutgoing && bubble.readReceipt !== ""
                anchors.verticalCenter: parent.verticalCenter
            }

        }

    }

}
