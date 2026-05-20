package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"log/slog"
	"net"
	"net/rpc"
	"net/rpc/jsonrpc"
	"os"
	"os/signal"
	"path/filepath"
	"reflect"
	"syscall"

	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	"greenline.brennoflavio/daemon/avatarsync"
	"greenline.brennoflavio/daemon/eventstore"
	"greenline.brennoflavio/daemon/notify"
	"greenline.brennoflavio/daemon/waconn"
)

type helperNotification struct {
	EventType string          `json:"event_type"`
	Event     json.RawMessage `json:"event"`
	ChatJID   string          `json:"chat_jid,omitempty"`
	ChatName  string          `json:"chat_name,omitempty"`
	Icon      string          `json:"icon,omitempty"`
	Muted     bool            `json:"muted"`
}

func notificationIconPath(cacheDir, jid string) string {
	if jid == "" {
		return ""
	}
	icon := avatarsync.AvatarJPGPath(cacheDir, jid)
	if _, err := os.Stat(icon); err != nil {
		return ""
	}
	return icon
}

func buildHelperNotificationPayload(client *waconn.Client, cacheDir string, evt interface{}, eventType string, data []byte) ([]byte, bool, error) {
	ctx := context.Background()
	envelope := helperNotification{
		EventType: eventType,
		Event:     json.RawMessage(data),
	}

	switch msg := evt.(type) {
	case *events.Message:
		if msg.Info.IsFromMe || msg.Info.Chat == types.StatusBroadcastJID || msg.Info.Chat.Server == types.NewsletterServer {
			return nil, false, nil
		}
		chatJID := client.ResolveJID(ctx, msg.Info.Chat).String()
		envelope.ChatJID = chatJID
		envelope.Icon = notificationIconPath(cacheDir, chatJID)
		envelope.Muted = client.IsMuted(ctx, msg.Info.Chat)
		if msg.Info.Chat.Server == types.GroupServer {
			groupName := msg.Info.Chat.User
			if groupInfo, err := client.GetGroupInfo(ctx, msg.Info.Chat); err == nil && groupInfo.Name != "" {
				groupName = groupInfo.Name
			}
			envelope.ChatName = groupName
		}
	case *events.UndecryptableMessage:
		if msg.Info.IsFromMe || msg.Info.Chat == types.StatusBroadcastJID || msg.Info.Chat.Server == types.NewsletterServer {
			return nil, false, nil
		}
		chatJID := client.ResolveJID(ctx, msg.Info.Chat).String()
		envelope.ChatJID = chatJID
		envelope.Icon = notificationIconPath(cacheDir, chatJID)
		envelope.Muted = client.IsMuted(ctx, msg.Info.Chat)
		if msg.Info.Chat.Server == types.GroupServer {
			groupName := msg.Info.Chat.User
			if groupInfo, err := client.GetGroupInfo(ctx, msg.Info.Chat); err == nil && groupInfo.Name != "" {
				groupName = groupInfo.Name
			}
			envelope.ChatName = groupName
		}
	case *events.CallOffer:
		chatJID := client.ResolveJID(ctx, msg.CallCreator).String()
		envelope.ChatJID = chatJID
		envelope.Icon = notificationIconPath(cacheDir, chatJID)
	default:
		return nil, false, nil
	}

	payload, err := json.Marshal(envelope)
	if err != nil {
		return nil, false, err
	}
	return payload, true, nil
}

var GitCommit string

func defaultSocketPath() string {
	if dir := os.Getenv("XDG_RUNTIME_DIR"); dir != "" {
		return filepath.Join(dir, "greenline-daemon.sock")
	}
	return "/tmp/greenline-daemon.sock"
}

func main() {
	socketPath := flag.String("socket", defaultSocketPath(), "Unix socket path")
	dataDir := flag.String("data-dir", "", "Data directory for persistent storage")
	cacheDir := flag.String("cache-dir", "", "Cache directory for avatars and temporary files")
	appID := flag.String("app-id", "", "Ubuntu Touch app ID for push notifications (e.g. com.example.app_myapp)")
	flag.Parse()

	if *dataDir == "" {
		log.Fatal("--data-dir is required")
	}

	if *cacheDir == "" {
		log.Fatal("--cache-dir is required")
	}

	if err := os.MkdirAll(*dataDir, 0700); err != nil {
		log.Fatal(err)
	}

	logger := slog.Default()

	dbPath := filepath.Join(*dataDir, "greenline.db")
	client, err := waconn.New(dbPath, logger)
	if err != nil {
		log.Fatal(err)
	}

	eventsDBPath := filepath.Join(*dataDir, "events.db")
	evStore, err := eventstore.New(eventsDBPath)
	if err != nil {
		log.Fatal(err)
	}

	var notifier *notify.Notifier
	if *appID != "" {
		n, err := notify.New(*appID)
		if err != nil {
			logger.Warn("notifications disabled", "error", err)
		} else {
			notifier = n
		}
	}

	syncer := avatarsync.New(client, *cacheDir, logger)
	svc := &Service{client: client, eventStore: evStore, syncer: syncer, notifier: notifier, cacheDir: *cacheDir}

	client.AddEventHandler(func(evt interface{}) {
		switch msg := evt.(type) {
		case *events.Disconnected, *events.LoggedOut, *events.StreamReplaced,
			*events.ClientOutdated, *events.TemporaryBan:
			return
		case *events.Message:
			if err := client.NormalizeMessageEdit(context.Background(), msg); err != nil {
				logger.Warn("failed to normalize edited message", "message_id", msg.Info.ID, "error", err)
			}
		}

		t := reflect.TypeOf(evt)
		if t.Kind() == reflect.Ptr {
			t = t.Elem()
		}
		typeName := t.Name()
		data, err := json.Marshal(evt)
		if err != nil {
			logger.Error("failed to marshal event", "type", typeName, "error", err)
			return
		}
		if err := evStore.Insert(typeName, data); err != nil {
			logger.Error("failed to store event", "type", typeName, "error", err)
		}

		if notifier == nil {
			return
		}
		payload, ok, err := buildHelperNotificationPayload(client, *cacheDir, evt, typeName, data)
		if err != nil {
			logger.Error("failed to build helper notification payload", "type", typeName, "error", err)
			return
		}
		if !ok {
			return
		}
		if err := notifier.Post(payload); err != nil {
			logger.Error("failed to post helper notification payload", "type", typeName, "error", err)
		}
	})

	ctx, cancel := context.WithCancel(context.Background())
	restartCh := make(chan struct{})
	go func() {
		client.ConnectWithRetry(ctx, svc.setQR)
		if ctx.Err() == nil {
			close(restartCh)
		}
	}()
	go syncer.Run(ctx)

	if err := rpc.Register(svc); err != nil {
		log.Fatal(err)
	}

	os.Remove(*socketPath)

	listener, err := net.Listen("unix", *socketPath)
	if err != nil {
		log.Fatal(err)
	}
	defer os.Remove(*socketPath)

	if err := os.Chmod(*socketPath, 0600); err != nil {
		log.Fatal(err)
	}

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		select {
		case <-sigCh:
		case <-restartCh:
			log.Println("Connection lost, exiting for restart")
		}
		cancel()
		client.Disconnect()
		evStore.Close()
		if notifier != nil {
			notifier.Close()
		}
		listener.Close()
	}()

	log.Printf("Listening on %s", *socketPath)

	for {
		conn, err := listener.Accept()
		if err != nil {
			break
		}
		go jsonrpc.ServeConn(conn)
	}

	select {
	case <-restartCh:
		os.Exit(1)
	default:
	}
}
