import Lomiri.Components 1.3
import QtQuick 2.7

Item {
    id: root

    property string text: ""
    property string copyableText: text
    property bool isOutgoing: false
    property bool edited: false
    property string timestamp: ""
    property string readReceipt: ""
    property string sendStatus: ""
    property bool expanded: false
    property int collapsedLineCount: 10
    readonly property real maxBubbleWidth: parent ? parent.width - units.gu(10) : 0
    readonly property bool shouldCollapse: fullHeightMeasure.implicitHeight > collapsedHeightMeasure.implicitHeight + units.gu(0.1)

    width: parent ? parent.width : 0
    height: wrapper.height + units.gu(0.5)

    Rectangle {
        id: wrapper

        width: Math.min(Math.max(textMeasure.implicitWidth + units.gu(2), footerRow.implicitWidth + units.gu(1)), root.maxBubbleWidth)
        height: contentColumn.implicitHeight + units.gu(1)
        color: root.isOutgoing ? "#dcf8c6" : "#d4e6f9"
        radius: units.gu(1)

        anchors {
            right: root.isOutgoing ? parent.right : undefined
            left: root.isOutgoing ? undefined : parent.left
            rightMargin: root.isOutgoing ? units.gu(2) : units.gu(8)
            leftMargin: root.isOutgoing ? units.gu(8) : units.gu(2)
        }

        Column {
            id: contentColumn

            anchors {
                fill: parent
                margins: units.gu(0.5)
            }

            Label {
                id: textMeasure

                visible: false
                text: root.text
                fontSize: "small"
            }

            Label {
                id: fullHeightMeasure

                visible: false
                text: root.text
                fontSize: "small"
                wrapMode: Text.Wrap
                width: parent.width
            }

            Label {
                id: collapsedHeightMeasure

                visible: false
                text: root.text
                fontSize: "small"
                wrapMode: Text.Wrap
                width: parent.width
                maximumLineCount: root.collapsedLineCount
                elide: Text.ElideRight
            }

            Label {
                id: contentLabel

                text: root.text
                fontSize: "small"
                color: "#303030"
                wrapMode: Text.Wrap
                width: parent.width
                maximumLineCount: root.shouldCollapse && !root.expanded ? root.collapsedLineCount : 2.14748e+09
                elide: root.shouldCollapse && !root.expanded ? Text.ElideRight : Text.ElideNone
            }

            Column {
                visible: root.shouldCollapse
                width: parent.width
                spacing: 0

                Item {
                    width: 1
                    height: toggleLabel.implicitHeight
                }

                Item {
                    width: parent.width
                    height: toggleLabel.implicitHeight + units.gu(0.6)

                    Label {
                        id: toggleLabel

                        text: root.expanded ? i18n.tr("Show less") : i18n.tr("Show more")
                        fontSize: "small"
                        color: LomiriColors.blue

                        anchors {
                            left: parent.left
                            verticalCenter: parent.verticalCenter
                        }

                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.expanded = !root.expanded
                    }

                }

            }

            Item {
                width: 1
                height: units.gu(1.5)
            }

        }

        Row {
            id: footerRow

            spacing: units.gu(0.3)

            anchors {
                right: parent.right
                bottom: parent.bottom
                rightMargin: units.gu(0.5)
                bottomMargin: units.gu(0.3)
            }

            Label {
                text: i18n.tr("edited")
                fontSize: "xx-small"
                color: "#999999"
                visible: root.edited
                anchors.verticalCenter: parent.verticalCenter
            }

            Label {
                text: root.timestamp
                fontSize: "xx-small"
                color: "#999999"
                anchors.verticalCenter: parent.verticalCenter
            }

            Icon {
                name: "close"
                height: units.gu(1.4)
                width: units.gu(1.4)
                color: LomiriColors.lightRed
                visible: root.isOutgoing && root.sendStatus === "failed"
                anchors.verticalCenter: parent.verticalCenter
            }

            Icon {
                name: root.readReceipt === "sent" ? "message-sent" : "tick"
                height: units.gu(1.4)
                width: units.gu(1.4)
                color: root.readReceipt === "read" ? LomiriColors.lightBlue : "#999999"
                visible: root.isOutgoing && root.sendStatus !== "failed" && root.readReceipt !== ""
                anchors.verticalCenter: parent.verticalCenter
            }

        }

    }

}
