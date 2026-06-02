import Lomiri.Components 1.3
import QtGraphicalEffects 1.0
import QtQuick 2.7

Item {
    id: bubble

    default property alias content: contentColumn.children
    property string copyableText: ""
    property bool isOutgoing: false
    property bool isGroup: false
    property bool edited: false
    property bool hasReactions: false
    property string timestamp: ""
    property string readReceipt: ""
    property string sendStatus: ""
    property string senderName: ""
    property string senderPhoto: ""
    property real preferredBubbleWidth: -1
    property string replyToId: ""
    property string replyToSender: ""
    property string replyToText: ""
    property string formattedReplyToText: ""
    property bool showSender: isGroup && !isOutgoing && senderName !== ""
    property color bubbleColor: isOutgoing ? "#dcf8c6" : "#d4e6f9"

    signal replyClicked(string messageId)

    width: parent.width
    height: wrapper.height + units.gu(0.5)

    Rectangle {
        id: avatar

        width: units.gu(3.5)
        height: units.gu(3.5)
        radius: width / 2
        color: theme.palette.normal.base
        visible: bubble.showSender

        anchors {
            left: parent.left
            bottom: wrapper.bottom
            leftMargin: units.gu(1)
        }

        Image {
            id: avatarImg

            anchors.fill: parent
            source: bubble.senderPhoto || ""
            fillMode: Image.PreserveAspectCrop
            visible: false
        }

        Rectangle {
            id: avatarMask

            anchors.fill: parent
            radius: width / 2
            visible: false
        }

        OpacityMask {
            anchors.fill: parent
            source: avatarImg
            maskSource: avatarMask
            visible: !!bubble.senderPhoto
        }

        Icon {
            anchors.centerIn: parent
            name: "contact"
            width: units.gu(2)
            height: units.gu(2)
            color: theme.palette.normal.backgroundSecondaryText
            visible: !bubble.senderPhoto
        }

    }

    Rectangle {
        id: wrapper

        width: Math.min(Math.max(preferredBubbleWidth > 0 ? preferredBubbleWidth : innerColumn.implicitWidth + units.gu(2), footerRow.implicitWidth + units.gu(1)), parent.width - units.gu(10))
        height: innerColumn.implicitHeight + units.gu(1)
        color: bubble.bubbleColor
        radius: units.gu(1)

        anchors {
            right: isOutgoing ? parent.right : undefined
            left: isOutgoing ? undefined : parent.left
            rightMargin: isOutgoing ? units.gu(2) : units.gu(8)
            leftMargin: isOutgoing ? units.gu(8) : (bubble.showSender ? units.gu(5.5) : units.gu(2))
        }

        Column {
            id: innerColumn

            spacing: units.gu(0.3)

            anchors {
                fill: parent
                margins: units.gu(0.5)
            }

            Rectangle {
                visible: bubble.replyToId !== ""
                width: parent.width
                height: replyColumn.height + units.gu(0.8)
                radius: units.gu(0.5)
                color: Qt.rgba(0, 0, 0, 0.06)

                MouseArea {
                    anchors.fill: parent
                    onClicked: bubble.replyClicked(bubble.replyToId)
                }

                Rectangle {
                    id: replyBar

                    width: units.gu(0.3)
                    height: parent.height
                    radius: units.gu(0.15)
                    color: LomiriColors.blue
                }

                Column {
                    id: replyColumn

                    spacing: units.gu(0.1)

                    anchors {
                        left: replyBar.right
                        right: parent.right
                        top: parent.top
                        leftMargin: units.gu(0.6)
                        rightMargin: units.gu(0.5)
                        topMargin: units.gu(0.4)
                    }

                    Label {
                        text: bubble.replyToSender
                        fontSize: "small"
                        font.bold: true
                        color: LomiriColors.blue
                        elide: Text.ElideRight
                        width: parent.width
                        visible: text !== ""
                    }

                    Label {
                        text: bubble.replyToText
                        textFormat: Text.PlainText
                        fontSize: "small"
                        color: "#666666"
                        elide: Text.ElideRight
                        maximumLineCount: 1
                        wrapMode: Text.NoWrap
                        width: parent.width
                        visible: text !== ""
                    }

                }

            }

            Label {
                text: bubble.senderName
                fontSize: "x-small"
                font.bold: true
                color: LomiriColors.blue
                visible: bubble.showSender
                elide: Text.ElideRight
                width: parent.width
            }

            Column {
                id: contentColumn

                spacing: units.gu(0.3)
                width: parent.width
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
                visible: bubble.edited
                anchors.verticalCenter: parent.verticalCenter
            }

            Icon {
                name: "like"
                height: units.gu(1.2)
                width: units.gu(1.2)
                color: "#999999"
                visible: bubble.hasReactions
                anchors.verticalCenter: parent.verticalCenter
            }

            Label {
                text: bubble.timestamp
                fontSize: "xx-small"
                color: "#999999"
                anchors.verticalCenter: parent.verticalCenter
            }

            Icon {
                name: "close"
                height: units.gu(1.4)
                width: units.gu(1.4)
                color: LomiriColors.lightRed
                visible: bubble.isOutgoing && bubble.sendStatus === "failed"
                anchors.verticalCenter: parent.verticalCenter
            }

            MessageReceiptIcon {
                height: units.gu(1.4)
                width: units.gu(1.4)
                readReceipt: bubble.readReceipt
                sendStatus: bubble.sendStatus
                inactiveColor: "#999999"
                activeColor: LomiriColors.lightBlue
                indicatorVisible: bubble.isOutgoing && bubble.sendStatus !== "failed"
                anchors.verticalCenter: parent.verticalCenter
            }

        }

    }

}
