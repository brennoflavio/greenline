/*
 * Copyright (C) 2025  Brenno Almeida
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; version 3.
 *
 * greenline is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

import Lomiri.Components 1.3
import QtQuick 2.7
import io.thp.pyotherside 1.4

MainView {
    id: root

    objectName: 'mainView'
    applicationName: 'greenline.brennoflavio'
    automaticOrientation: true
    width: units.gu(45)
    height: units.gu(75)

    PageStack {
        id: pageStack
    }

    Column {
        anchors.centerIn: parent
        spacing: units.gu(2)
        visible: pageStack.depth === 0

        Image {
            id: logo

            source: Qt.resolvedUrl("../assets/logo-no-bg.png")
            anchors.horizontalCenter: parent.horizontalCenter
            width: units.gu(20)
            height: units.gu(20)
            fillMode: Image.PreserveAspectFit
        }

    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                pageStack.push(Qt.resolvedUrl("ChatListPage.qml"));
            });
        }
        onError: {
            console.log('python error: ' + traceback);
        }
    }

}
