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

	waBinary "go.mau.fi/whatsmeow/binary"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	"greenline.brennoflavio/daemon/avatarsync"
	"greenline.brennoflavio/daemon/eventstore"
	"greenline.brennoflavio/daemon/notify"
	"greenline.brennoflavio/daemon/waconn"
)

func isVideoCall(data *waBinary.Node) bool {
	if data == nil {
		return false
	}
	for _, child := range data.GetChildren() {
		if child.Tag == "video" {
			return true
		}
	}
	return false
}

func extractBody(msg *events.Message) string {
	if msg.Message == nil {
		return ""
	}
	if s := msg.Message.GetConversation(); s != "" {
		return s
	}
	if etm := msg.Message.GetExtendedTextMessage(); etm != nil {
		if s := etm.GetText(); s != "" {
			return s
		}
	}
	if im := msg.Message.GetImageMessage(); im != nil {
		if c := im.GetCaption(); c != "" {
			return "📷 " + c
		}
		return "📷 Photo"
	}
	if vm := msg.Message.GetVideoMessage(); vm != nil {
		if c := vm.GetCaption(); c != "" {
			return "🎥 " + c
		}
		return "🎥 Video"
	}
	if msg.Message.GetAudioMessage() != nil {
		return "🎵 Audio"
	}
	if dm := msg.Message.GetDocumentMessage(); dm != nil {
		if c := dm.GetCaption(); c != "" {
			return "📄 " + c
		}
		return "📄 Document"
	}
	if msg.Message.GetStickerMessage() != nil {
		return "🏷️ Sticker"
	}
	if msg.Message.GetContactMessage() != nil {
		return "👤 Contact"
	}
	if msg.Message.GetLocationMessage() != nil {
		return "📍 Location"
	}
	return ""
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

	client.AddEventHandler(func(evt interface{}) {
		switch evt.(type) {
		case *events.Disconnected, *events.LoggedOut, *events.StreamReplaced,
			*events.ClientOutdated, *events.TemporaryBan:
			return
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
		if msg, ok := evt.(*events.Message); ok {
			if msg.Info.IsFromMe {
				return
			}
			if msg.Info.Chat == types.StatusBroadcastJID {
				return
			}
			if msg.Info.Chat.Server == types.NewsletterServer {
				return
			}
			if client.IsMuted(context.Background(), msg.Info.Chat) {
				return
			}
			body := extractBody(msg)
			if body == "" {
				return
			}
			summary := msg.Info.PushName
			if summary == "" {
				summary = msg.Info.Sender.User
			}
			chatJID := client.ResolveJID(context.Background(), msg.Info.Chat)
			icon := avatarsync.AvatarJPGPath(*cacheDir, chatJID.String())
			if _, err := os.Stat(icon); err != nil {
				icon = ""
			}
			if err := notifier.Post(summary, body, icon, chatJID.String()); err != nil {
				logger.Error("failed to send notification", "error", err)
			}
		}
		if call, ok := evt.(*events.CallOffer); ok {
			ctx := context.Background()
			callerJID := client.ResolveJID(ctx, call.CallCreator)
			summary := callerJID.User
			if contact, err := client.GetContact(ctx, callerJID); err == nil {
				if name := contactDisplayName(callerJID.String(), contact.FullName, contact.PushName, contact.BusinessName); name != callerJID.String() {
					summary = name
				}
			}
			body := "Incoming audio call — answer on your primary phone"
			if isVideoCall(call.Data) {
				body = "Incoming video call — answer on your primary phone"
			}
			icon := avatarsync.AvatarJPGPath(*cacheDir, callerJID.String())
			if _, err := os.Stat(icon); err != nil {
				icon = ""
			}
			if err := notifier.Post(summary, body, icon, callerJID.String()); err != nil {
				logger.Error("failed to send call notification", "error", err)
			}
		}
	})

	syncer := avatarsync.New(client, *cacheDir, logger)
	svc := &Service{client: client, eventStore: evStore, syncer: syncer, cacheDir: *cacheDir}

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
