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
import Lomiri.Content 1.3
import QtQuick 2.7
import io.thp.pyotherside 1.4
import "ut_components"

MainView {
    id: root

    property bool isAuthenticating: false
    property bool initComplete: false
    property bool isLoggedIn: false
    property string pendingChatUri: ""
    property string pendingSharedFilePath: ""
    property string pendingSharedMediaType: ""

    function sharedFilePathFromUrl(fileUrl) {
        if (!fileUrl)
            return "";

        var normalizedUrl = fileUrl.toString();
        if (normalizedUrl.indexOf("file://") === 0)
            normalizedUrl = normalizedUrl.substring(7);

        return decodeURIComponent(normalizedUrl);
    }

    function normalizeSharedMediaType(contentType, filePath) {
        if (contentType === ContentType.Pictures)
            return "image";

        if (contentType === ContentType.Videos)
            return "video";

        if (contentType === ContentType.Documents)
            return "document";

        var lowerPath = (filePath || "").toLowerCase();
        if (/(\.jpg|\.jpeg|\.png|\.gif|\.bmp|\.webp|\.heic|\.heif|\.avif)$/i.test(lowerPath))
            return "image";

        if (/(\.mp4|\.mov|\.mkv|\.webm|\.avi|\.3gp|\.m4v)$/i.test(lowerPath))
            return "video";

        return lowerPath !== "" ? "document" : "";
    }

    function routePendingShare() {
        if (pendingSharedFilePath === "" || pendingSharedMediaType === "")
            return ;

        var filePath = pendingSharedFilePath;
        var mediaType = pendingSharedMediaType;
        pendingSharedFilePath = "";
        pendingSharedMediaType = "";
        pageStack.push(Qt.resolvedUrl("ChatListPage.qml"), {
            "shareSelectionMode": true,
            "shareFilePath": filePath,
            "shareMediaType": mediaType
        });
    }

    function handleInboundTransfer(transfer) {
        if (!transfer || !transfer.items || transfer.items.length === 0) {
            if (transfer)
                transfer.state = ContentTransfer.Charged;

            shareToast.show(i18n.tr("No shared file was received"));
            return ;
        }
        var filePath = sharedFilePathFromUrl(transfer.items[0].url);
        var mediaType = normalizeSharedMediaType(transfer.contentType, filePath);
        if (transfer.items.length > 1)
            shareToast.show(i18n.tr("Only the first shared item will be used"));

        if (filePath === "") {
            shareToast.show(i18n.tr("Unable to open the shared file"));
            transfer.state = ContentTransfer.Charged;
            return ;
        }
        if (mediaType === "") {
            shareToast.show(i18n.tr("Unsupported shared item"));
            transfer.state = ContentTransfer.Charged;
            return ;
        }
        pendingSharedFilePath = filePath;
        pendingSharedMediaType = mediaType;
        transfer.state = ContentTransfer.Charged;
        if (isLoggedIn)
            routePendingShare();

    }

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
                "initialUnreadCount": result.unread_count || 0,
                "initialFirstUnreadMessageId": result.first_unread_message_id || ""
            });

        });
    }

    onIsLoggedInChanged: {
        if (!isLoggedIn)
            return ;

        if (pendingChatUri !== "") {
            openChatFromUri(pendingChatUri);
            pendingChatUri = "";
        }
        if (pendingSharedFilePath !== "")
            Qt.callLater(function() {
            if (isLoggedIn && pendingSharedFilePath !== "")
                routePendingShare();

        });

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
        target: ContentHub
        onImportRequested: handleInboundTransfer(transfer)
        onShareRequested: handleInboundTransfer(transfer)
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

    Connections {
        target: Qt.application
        onAboutToQuit: {
            python.call('main.handle_application_exit', [], function() {
            });
        }
    }

    Rectangle {
        anchors.fill: parent
        z: 100
        color: "#30a05a"
        visible: !initComplete

        Image {
            source: Qt.resolvedUrl("../assets/logo-no-bg.png")
            anchors.centerIn: parent
            width: units.gu(20)
            height: units.gu(20)
            fillMode: Image.PreserveAspectFit
        }

    }

    Toast {
        id: shareToast

        z: 200
    }

    Python {
        id: python

        Component.onCompleted: {
            addImportPath(Qt.resolvedUrl('../src/'));
            importModule('main', function() {
                python.call('main.run_storage_migrations', [], function() {
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
