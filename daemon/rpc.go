package main

import (
	"context"
	"encoding/base64"
	"sort"
	"strings"
	"sync"

	"os"

	qrcode "github.com/skip2/go-qrcode"
	"greenline.brennoflavio/daemon/avatarsync"
	"greenline.brennoflavio/daemon/eventstore"
	"greenline.brennoflavio/daemon/waconn"
)

type Service struct {
	client     *waconn.Client
	eventStore *eventstore.Store
	cacheDir   string
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

// Contact types

type Contact struct {
	JID          string `json:"jid"`
	DisplayName  string `json:"display_name"`
	FirstName    string `json:"first_name"`
	FullName     string `json:"full_name"`
	PushName     string `json:"push_name"`
	BusinessName string `json:"business_name"`
	AvatarPath   string `json:"avatar_path"`
}

func contactDisplayName(jid, fullName, pushName, businessName string) string {
	switch {
	case fullName != "":
		return fullName
	case pushName != "":
		return pushName
	case businessName != "":
		return businessName
	default:
		return jid
	}
}

// GetContacts returns all contacts from the local whatsmeow store, sorted by display name.

type GetContactsReply struct {
	Contacts []Contact
}

func (s *Service) GetContacts(args *struct{}, reply *GetContactsReply) error {
	ctx := context.Background()
	all, err := s.client.GetAllContacts(ctx)
	if err != nil {
		return err
	}

	contacts := make([]Contact, 0, len(all))
	for jid, info := range all {
		jidStr := jid.String()
		avatarPath := ""
		jpgPath := avatarsync.AvatarJPGPath(s.cacheDir, jidStr)
		if _, err := os.Stat(jpgPath); err == nil {
			avatarPath = jpgPath
		}
		contacts = append(contacts, Contact{
			JID:          jidStr,
			DisplayName:  contactDisplayName(jidStr, info.FullName, info.PushName, info.BusinessName),
			FirstName:    info.FirstName,
			FullName:     info.FullName,
			PushName:     info.PushName,
			BusinessName: info.BusinessName,
			AvatarPath:   avatarPath,
		})
	}

	sort.Slice(contacts, func(i, j int) bool {
		return strings.ToLower(contacts[i].DisplayName) < strings.ToLower(contacts[j].DisplayName)
	})

	reply.Contacts = contacts
	return nil
}
