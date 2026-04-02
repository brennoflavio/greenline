package main

import (
	"context"
	"encoding/base64"
	"fmt"
	"mime"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	qrcode "github.com/skip2/go-qrcode"
	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store"
	"google.golang.org/protobuf/proto"
	"greenline.brennoflavio/daemon/avatarsync"
	"greenline.brennoflavio/daemon/eventstore"
	"greenline.brennoflavio/daemon/waconn"

	"go.mau.fi/whatsmeow/types"
)

type Service struct {
	client     *waconn.Client
	eventStore *eventstore.Store
	syncer     *avatarsync.Syncer
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

// SyncAvatar types

type SyncAvatarArgs struct {
	JID string
}

type SyncAvatarReply struct {
	AvatarPath string
}

func (s *Service) SyncAvatar(args *SyncAvatarArgs, reply *SyncAvatarReply) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	reply.AvatarPath = s.syncer.ForceSync(ctx, args.JID)
	return nil
}

// ChatSettings types

type GetChatSettingsArgs struct {
	ChatJID string
}

type GetChatSettingsReply struct {
	MutedUntil int64 `json:"MutedUntil"` // unix ms: 0 = not muted, -1 = forever
}

func (s *Service) GetChatSettings(args *GetChatSettingsArgs, reply *GetChatSettingsReply) error {
	jid, err := types.ParseJID(args.ChatJID)
	if err != nil {
		return fmt.Errorf("invalid chat JID: %w", err)
	}
	settings, err := s.client.GetChatSettings(context.Background(), jid)
	if err != nil {
		return fmt.Errorf("get chat settings: %w", err)
	}
	if !settings.Found || settings.MutedUntil.IsZero() {
		reply.MutedUntil = 0
	} else if settings.MutedUntil.Equal(store.MutedForever) {
		reply.MutedUntil = -1
	} else {
		reply.MutedUntil = settings.MutedUntil.UnixMilli()
	}
	return nil
}

// SetMuted types

type SetMutedArgs struct {
	ChatJID string
	Muted   bool
}

func (s *Service) SetMuted(args *SetMutedArgs, reply *struct{}) error {
	jid, err := types.ParseJID(args.ChatJID)
	if err != nil {
		return fmt.Errorf("invalid chat JID: %w", err)
	}
	return s.client.SetMuted(context.Background(), jid, args.Muted)
}

// DownloadMedia types

type DownloadMediaArgs struct {
	DirectPath    string
	MediaKey      string
	FileEncSHA256 string
	FileSHA256    string
	FileLength    int
	MediaType     string // "image", "video", "audio", "document", "sticker"
	Mimetype      string
	MessageID     string
	ChatID        string
	FileName      string
}

type DownloadMediaReply struct {
	FilePath string
}

var mediaTypeMap = map[string]whatsmeow.MediaType{
	"image":    whatsmeow.MediaImage,
	"video":    whatsmeow.MediaVideo,
	"audio":    whatsmeow.MediaAudio,
	"document": whatsmeow.MediaDocument,
	"sticker":  whatsmeow.MediaImage,
}

var mmsTypeMap = map[string]string{
	"image":    "image",
	"video":    "video",
	"audio":    "audio",
	"document": "document",
	"sticker":  "image",
}

func extensionFromMimetype(mimetype string) string {
	exts, err := mime.ExtensionsByType(mimetype)
	if err == nil && len(exts) > 0 {
		return exts[0]
	}
	parts := strings.SplitN(mimetype, "/", 2)
	if len(parts) == 2 {
		sub := parts[1]
		if sub == "ogg" || sub == "ogg; codecs=opus" {
			return ".ogg"
		}
		return "." + sub
	}
	return ".bin"
}

// SendMessage types

type SendMessageArgs struct {
	ChatJID string
	Type    string // "text", "image", "video", "audio", "sticker", "document"
	Text    string
}

type SendMessageReply struct {
	MessageID string
	Timestamp int64
}

func (s *Service) SendMessage(args *SendMessageArgs, reply *SendMessageReply) error {
	jid, err := types.ParseJID(args.ChatJID)
	if err != nil {
		return fmt.Errorf("invalid chat JID: %w", err)
	}

	var message *waE2E.Message
	switch args.Type {
	case "text":
		message = &waE2E.Message{
			Conversation: proto.String(args.Text),
		}
	default:
		return fmt.Errorf("unsupported message type: %s", args.Type)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	resp, err := s.client.SendMessage(ctx, jid, message)
	if err != nil {
		return fmt.Errorf("send failed: %w", err)
	}

	reply.MessageID = string(resp.ID)
	reply.Timestamp = resp.Timestamp.Unix()
	return nil
}

func (s *Service) DownloadMedia(args *DownloadMediaArgs, reply *DownloadMediaReply) error {
	wmMediaType, ok := mediaTypeMap[args.MediaType]
	if !ok {
		return fmt.Errorf("unknown media type: %s", args.MediaType)
	}
	mmsType := mmsTypeMap[args.MediaType]

	mediaKey, err := base64.StdEncoding.DecodeString(args.MediaKey)
	if err != nil {
		return fmt.Errorf("invalid media key: %w", err)
	}
	encSHA256, err := base64.StdEncoding.DecodeString(args.FileEncSHA256)
	if err != nil {
		return fmt.Errorf("invalid file enc SHA256: %w", err)
	}
	fileSHA256, err := base64.StdEncoding.DecodeString(args.FileSHA256)
	if err != nil {
		return fmt.Errorf("invalid file SHA256: %w", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	data, err := s.client.DownloadMediaWithPath(ctx, args.DirectPath, encSHA256, fileSHA256, mediaKey, args.FileLength, wmMediaType, mmsType)
	if err != nil {
		return fmt.Errorf("download failed: %w", err)
	}

	ext := extensionFromMimetype(args.Mimetype)
	dir := filepath.Join(s.cacheDir, "media", args.ChatID)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return fmt.Errorf("failed to create media dir: %w", err)
	}
	ts := fmt.Sprintf("%d", time.Now().Unix())
	baseName := args.MessageID
	if args.FileName != "" {
		name := strings.TrimSuffix(args.FileName, filepath.Ext(args.FileName))
		baseName = name + "_" + ts
	} else {
		baseName = args.MessageID + "_" + ts
	}
	filePath := filepath.Join(dir, baseName+ext)
	if err := os.WriteFile(filePath, data, 0600); err != nil {
		return fmt.Errorf("failed to write media file: %w", err)
	}

	reply.FilePath = filePath
	return nil
}
