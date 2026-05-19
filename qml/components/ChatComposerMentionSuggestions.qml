import Lomiri.Components 1.3
import QtQuick 2.7

Rectangle {
    id: root

    property var candidates: []
    property bool suggestionPointerDown: false

    signal candidateSelected(var candidate)

    height: Math.min(candidates.length, 4) * units.gu(5)
    radius: units.gu(0.6)
    color: theme.palette.normal.base
    border.width: units.dp(1)
    border.color: theme.palette.normal.backgroundSecondaryText
    clip: true

    ListView {
        anchors.fill: parent
        model: root.candidates
        interactive: root.candidates.length > 4

        delegate: ListItem {
            width: parent ? parent.width : root.width
            height: units.gu(5)
            divider.visible: index < root.candidates.length - 1

            MouseArea {
                anchors.fill: parent
                onPressed: root.suggestionPointerDown = true
                onCanceled: root.suggestionPointerDown = false
                onReleased: root.suggestionPointerDown = false
                onClicked: root.candidateSelected(modelData)
            }

            Row {
                spacing: units.gu(1)

                anchors {
                    left: parent.left
                    leftMargin: units.gu(1)
                    right: parent.right
                    rightMargin: units.gu(1)
                    verticalCenter: parent.verticalCenter
                }

                Rectangle {
                    width: units.gu(3.2)
                    height: units.gu(3.2)
                    radius: width / 2
                    color: theme.palette.normal.background
                    visible: !candidatePhoto.visible

                    Label {
                        anchors.centerIn: parent
                        text: String(modelData && modelData.label || "").slice(0, 1).toUpperCase()
                        font.bold: true
                        color: theme.palette.normal.backgroundText
                    }

                }

                Image {
                    id: candidatePhoto

                    width: units.gu(3.2)
                    height: units.gu(3.2)
                    fillMode: Image.PreserveAspectCrop
                    source: String(modelData && modelData.photo || "")
                    visible: source !== ""
                }

                Label {
                    width: parent.width - units.gu(5.5)
                    text: String(modelData && modelData.label || "")
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }

            }

        }

    }

}
