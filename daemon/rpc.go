package main

import (
	"context"
	"encoding/base64"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"os"

	qrcode "github.com/skip2/go-qrcode"
	"greenline.brennoflavio/daemon/avatarsync"
	"greenline.brennoflavio/daemon/eventstore"
	"greenline.brennoflavio/daemon/waconn"

	"go.mau.fi/whatsmeow/types"
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

// MarkRead types

type MarkReadArgs struct {
	ChatJID    string
	SenderJID  string
	MessageIDs []string
}

func (s *Service) MarkRead(args *MarkReadArgs, reply *struct{}) error {
	chat, err := types.ParseJID(args.ChatJID)
	if err != nil {
		return fmt.Errorf("invalid chat JID: %w", err)
	}
	var sender types.JID
	if args.SenderJID != "" {
		sender, err = types.ParseJID(args.SenderJID)
		if err != nil {
			return fmt.Errorf("invalid sender JID: %w", err)
		}
	}
	return s.client.MarkRead(context.Background(), args.MessageIDs, time.Now(), chat, sender)
}

// EnsureJID types

type EnsureJIDArgs struct {
	JID string
}

type EnsureJIDReply struct {
	JID string
}

func (s *Service) EnsureJID(args *EnsureJIDArgs, reply *EnsureJIDReply) error {
	jid, err := types.ParseJID(args.JID)
	if err != nil {
		return fmt.Errorf("invalid JID: %w", err)
	}
	if jid.Server == types.HiddenUserServer {
		pn, err := s.client.GetPNForLID(context.Background(), jid)
		if err == nil && !pn.IsEmpty() {
			reply.JID = pn.String()
			return nil
		}
	}
	reply.JID = jid.String()
	return nil
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

// Group types

type Group struct {
	JID        string `json:"jid"`
	Name       string `json:"name"`
	Topic      string `json:"topic"`
	AvatarPath string `json:"avatar_path"`
}

type GetGroupsReply struct {
	Groups []Group
}

func (s *Service) GetGroups(args *struct{}, reply *GetGroupsReply) error {
	ctx := context.Background()
	joined, err := s.client.GetJoinedGroups(ctx)
	if err != nil {
		return err
	}

	groups := make([]Group, 0, len(joined))
	for _, info := range joined {
		jidStr := info.JID.String()
		if info.JID.Server != types.GroupServer {
			continue
		}
		avatarPath := ""
		jpgPath := avatarsync.AvatarJPGPath(s.cacheDir, jidStr)
		if _, err := os.Stat(jpgPath); err == nil {
			avatarPath = jpgPath
		}
		name := info.Name
		if name == "" {
			name = jidStr
		}
		groups = append(groups, Group{
			JID:        jidStr,
			Name:       name,
			Topic:      info.Topic,
			AvatarPath: avatarPath,
		})
	}

	sort.Slice(groups, func(i, j int) bool {
		return strings.ToLower(groups[i].Name) < strings.ToLower(groups[j].Name)
	})

	reply.Groups = groups
	return nil
}
