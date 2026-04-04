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

    property bool isAuthenticating: false
    property bool initComplete: false

    objectName: 'mainView'
    applicationName: 'greenline.brennoflavio'
    automaticOrientation: true
    width: units.gu(45)
    height: units.gu(75)

    PageStack {
        id: pageStack
    }

    Rectangle {
        anchors.fill: parent
        z: 100
        color: theme.palette.normal.background
        visible: !initComplete

        Image {
            source: Qt.resolvedUrl("../assets/logo-no-bg.png")
            anchors.centerIn: parent
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
                python.call('main.check_daemon_status', [], function(result) {
                    if (!result.installed || !result.active) {
                        initComplete = true;
                        pageStack.push(Qt.resolvedUrl("DaemonSetupPage.qml"), {
                            "daemonInstalled": result.installed
                        });
                        return ;
                    }
                    python.call('main.check_daemon_version', [], function() {
                        python.call('main.get_session_status', [], function(session) {
                            python.call('main.start_event_loop', [], function() {
                            });
                            if (session.logged_in)
                                pageStack.push(Qt.resolvedUrl("ChatListPage.qml"));
                            else
                                pageStack.push(Qt.resolvedUrl("AuthorizationPage.qml"));
                            initComplete = true;
                        });
                    });
                });
                setHandler('session-status', function(status) {
                    if (!status.logged_in && !isAuthenticating) {
                        pageStack.clear();
                        pageStack.push(Qt.resolvedUrl("AuthorizationPage.qml"));
                    }
                });
            });
        }
        onError: {
            console.log('python error: ' + traceback);
        }
    }

}
