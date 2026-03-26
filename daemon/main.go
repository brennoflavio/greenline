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

	"go.mau.fi/whatsmeow/types/events"
	"greenline.brennoflavio/daemon/eventstore"
	"greenline.brennoflavio/daemon/waconn"
)

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
	flag.Parse()

	if *dataDir == "" {
		log.Fatal("--data-dir is required")
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
	})

	svc := &Service{client: client, eventStore: evStore}

	ctx, cancel := context.WithCancel(context.Background())
	go client.ConnectWithRetry(ctx, svc.setQR)

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
		<-sigCh
		cancel()
		client.Disconnect()
		evStore.Close()
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
}
