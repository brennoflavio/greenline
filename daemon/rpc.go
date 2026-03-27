package main

import (
	"context"
	"encoding/base64"
	"sort"
	"strings"
	"sync"

	qrcode "github.com/skip2/go-qrcode"
	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/types"
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

// Contact types

type Contact struct {
	JID          string `json:"jid"`
	DisplayName  string `json:"display_name"`
	FirstName    string `json:"first_name"`
	FullName     string `json:"full_name"`
	PushName     string `json:"push_name"`
	BusinessName string `json:"business_name"`
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
		contacts = append(contacts, Contact{
			JID:          jidStr,
			DisplayName:  contactDisplayName(jidStr, info.FullName, info.PushName, info.BusinessName),
			FirstName:    info.FirstName,
			FullName:     info.FullName,
			PushName:     info.PushName,
			BusinessName: info.BusinessName,
		})
	}

	sort.Slice(contacts, func(i, j int) bool {
		return strings.ToLower(contacts[i].DisplayName) < strings.ToLower(contacts[j].DisplayName)
	})

	reply.Contacts = contacts
	return nil
}

// GetContactInfo returns a single contact's info including profile picture URL.

type GetContactInfoArgs struct {
	JID string
}

type ContactInfoResult struct {
	Contact
	ProfilePicURL string `json:"profile_pic_url"`
	ProfilePicID  string `json:"profile_pic_id"`
}

type GetContactInfoReply struct {
	Contact ContactInfoResult
	Found   bool
}

func (s *Service) GetContactInfo(args *GetContactInfoArgs, reply *GetContactInfoReply) error {
	ctx := context.Background()
	jid, err := types.ParseJID(args.JID)
	if err != nil {
		return err
	}

	info, err := s.client.GetContact(ctx, jid)
	if err != nil {
		return err
	}

	jidStr := jid.String()
	reply.Found = info.Found
	reply.Contact = ContactInfoResult{
		Contact: Contact{
			JID:          jidStr,
			DisplayName:  contactDisplayName(jidStr, info.FullName, info.PushName, info.BusinessName),
			FirstName:    info.FirstName,
			FullName:     info.FullName,
			PushName:     info.PushName,
			BusinessName: info.BusinessName,
		},
	}

	pic, err := s.client.GetProfilePictureInfo(ctx, jid, &whatsmeow.GetProfilePictureParams{
		Preview: true,
	})
	if err == nil && pic != nil {
		reply.Contact.ProfilePicURL = pic.URL
		reply.Contact.ProfilePicID = pic.ID
	}

	return nil
}

// GetProfilePicture returns the profile picture URL for a JID, with cache support via ExistingID.

type GetProfilePictureArgs struct {
	JID        string
	ExistingID string
}

type GetProfilePictureReply struct {
	URL string
	ID  string
}

func (s *Service) GetProfilePicture(args *GetProfilePictureArgs, reply *GetProfilePictureReply) error {
	ctx := context.Background()
	jid, err := types.ParseJID(args.JID)
	if err != nil {
		return err
	}

	pic, err := s.client.GetProfilePictureInfo(ctx, jid, &whatsmeow.GetProfilePictureParams{
		Preview:    true,
		ExistingID: args.ExistingID,
	})
	if err == nil && pic != nil {
		reply.URL = pic.URL
		reply.ID = pic.ID
	}

	return nil
}
