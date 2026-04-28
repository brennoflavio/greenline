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
    property bool isLoggedIn: false
    property string pendingChatUri: ""

    function openChatFromUri(uri) {
        var prefix = "greenline://chat/";
        if (uri.indexOf(prefix) !== 0)
            return ;

        var chatJid = decodeURIComponent(uri.substring(prefix.length));
        python.call('main.get_chat_info', [chatJid], function(result) {
            if (result.success)
                pageStack.push(Qt.resolvedUrl("ChatPage.qml"), {
                "chatId": result.id,
                "chatName": result.name,
                "chatPhoto": result.photo,
                "isGroup": result.is_group || false,
                "initialUnreadCount": result.unread_count || 0
            });

        });
    }

    onIsLoggedInChanged: {
        if (isLoggedIn && pendingChatUri !== "") {
            openChatFromUri(pendingChatUri);
            pendingChatUri = "";
        }
    }
    objectName: 'mainView'
    applicationName: 'greenline.brennoflavio'
    automaticOrientation: true
    width: units.gu(45)
    height: units.gu(75)

    PageStack {
        id: pageStack
    }

    Connections {
        target: UriHandler
        onOpened: {
            if (uris.length === 0)
                return ;

            var uri = uris[0];
            if (isLoggedIn)
                openChatFromUri(uri);
            else
                pendingChatUri = uri;
        }
    }

    Connections {
        target: Qt.application
        onStateChanged: {
            if (Qt.application.state === Qt.ApplicationActive)
                python.call('main.send_presence', [true], function() {
            });
            else
                python.call('main.send_presence', [false], function() {
            });
        }
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
                            if (session.logged_in) {
                                python.call('main.send_presence', [true], function() {
                                });
                                pageStack.push(Qt.resolvedUrl("ChatListPage.qml"));
                                isLoggedIn = true;
                                var args = Qt.application.arguments;
                                for (var i = 0; i < args.length; i++) {
                                    if (args[i].indexOf("greenline://") === 0) {
                                        openChatFromUri(args[i]);
                                        break;
                                    }
                                }
                            } else {
                                pageStack.push(Qt.resolvedUrl("AuthorizationPage.qml"));
                            }
                            initComplete = true;
                        });
                    });
                });
                setHandler('session-status', function(status) {
                    if (!status.logged_in && !isAuthenticating) {
                        isLoggedIn = false;
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
