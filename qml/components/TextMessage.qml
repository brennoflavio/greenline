import Lomiri.Components 1.3
import QtQuick 2.7

MessageBubble {
    id: root

    property string text: ""

    Label {
        text: root.text
        fontSize: "small"
        color: "#303030"
        wrapMode: Text.WordWrap
        width: parent.width
    }

    Item {
        width: 1
        height: units.gu(1.5)
    }

}
