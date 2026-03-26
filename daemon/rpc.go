package main

import (
	"encoding/base64"
	"sync"

	qrcode "github.com/skip2/go-qrcode"
	"greenline.brennoflavio/daemon/eventstore"
	"greenline.brennoflavio/daemon/waconn"
)

type Service struct {
	client     *waconn.Client
	eventStore *eventstore.Store
	mu         sync.RWMutex
	qrCode     string
}

func (s *Service) setQR(code string) {
	s.mu.Lock()
	s.qrCode = code
	s.mu.Unlock()
}

func (s *Service) Ping(args *struct{}, reply *string) error {
	*reply = "pong"
	return nil
}

func (s *Service) GetQR(args *struct{}, reply *string) error {
	s.mu.RLock()
	*reply = s.qrCode
	s.mu.RUnlock()
	return nil
}

type StatusReply struct {
	Status string
}

func (s *Service) GetStatus(args *struct{}, reply *StatusReply) error {
	if s.client.IsLoggedIn() {
		reply.Status = "connected"
		return nil
	}
	if s.client.IsConnected() {
		reply.Status = "connecting"
		return nil
	}
	s.mu.RLock()
	hasQR := s.qrCode != ""
	s.mu.RUnlock()
	if hasQR {
		reply.Status = "qr_pending"
		return nil
	}
	reply.Status = "disconnected"
	return nil
}

type VersionReply struct {
	GitCommit string
}

func (s *Service) GetVersion(args *struct{}, reply *VersionReply) error {
	reply.GitCommit = GitCommit
	return nil
}

type SessionStatusReply struct {
	LoggedIn bool
	QRCode   string
	QRImage  string
}

func (s *Service) GetSessionStatus(args *struct{}, reply *SessionStatusReply) error {
	reply.LoggedIn = s.client.IsLoggedIn()
	if !reply.LoggedIn {
		s.mu.RLock()
		raw := s.qrCode
		s.mu.RUnlock()
		reply.QRCode = raw
		if raw != "" {
			png, err := qrcode.Encode(raw, qrcode.Medium, 256)
			if err == nil {
				reply.QRImage = base64.StdEncoding.EncodeToString(png)
			}
		}
	}
	return nil
}

type ListEventsArgs struct {
	AfterID int64
	Limit   int
}

type ListEventsReply struct {
	Events []eventstore.Event
}

func (s *Service) ListEvents(args *ListEventsArgs, reply *ListEventsReply) error {
	evts, err := s.eventStore.List(args.AfterID, args.Limit)
	if err != nil {
		return err
	}
	reply.Events = evts
	return nil
}

type DeleteEventsArgs struct {
	UpToID int64
}

func (s *Service) DeleteEvents(args *DeleteEventsArgs, reply *struct{}) error {
	return s.eventStore.Delete(args.UpToID)
}
