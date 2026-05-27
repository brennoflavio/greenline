package main

import (
	"context"
	"encoding/base64"
	"errors"
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
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
	"greenline.brennoflavio/daemon/avatarsync"
	"greenline.brennoflavio/daemon/eventstore"
	"greenline.brennoflavio/daemon/notify"
	"greenline.brennoflavio/daemon/waconn"

	"go.mau.fi/whatsmeow/types"
)

type Service struct {
	client     *waconn.Client
	eventStore *eventstore.Store
	syncer     *avatarsync.Syncer
	notifier   *notify.Notifier
	cacheDir   string
	mu         sync.RWMutex
	qrCode     string
}

func (s *Service) setQR(code string) {
	s.mu.Lock()
	s.qrCode = code
	s.mu.Unlock()
}

var ErrNotLoggedIn = errors.New("not logged in")

func (s *Service) requireLogin() error {
	if !s.client.IsLoggedIn() {
		return ErrNotLoggedIn
	}
	return nil
}

func (s *Service) Ping(args *struct{}, reply *string) error {
	*reply = "pong"
	return nil
}

func (s *Service) Logout(args *struct{}, reply *struct{}) error {
	return s.client.Logout(context.Background())
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
	if err := s.requireLogin(); err != nil {
		return err
	}
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
	if err := s.requireLogin(); err != nil {
		return err
	}
	jid, err := types.ParseJID(args.JID)
	if err != nil {
		return fmt.Errorf("invalid JID: %w", err)
	}
	reply.JID = s.client.ResolveJID(context.Background(), jid).String()
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
	if err := s.requireLogin(); err != nil {
		return err
	}
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
	if err := s.requireLogin(); err != nil {
		return err
	}
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

type GetGroupParticipantsArgs struct {
	ChatJID string
}

type GroupParticipant struct {
	JID            string `json:"jid"`
	PhoneNumberJID string `json:"phone_number_jid"`
	LIDJID         string `json:"lid_jid"`
	DisplayName    string `json:"display_name"`
	IsAdmin        bool   `json:"is_admin"`
	IsSuperAdmin   bool   `json:"is_super_admin"`
}

type GetGroupParticipantsReply struct {
	Participants []GroupParticipant
}

func (s *Service) GetGroupParticipants(args *GetGroupParticipantsArgs, reply *GetGroupParticipantsReply) error {
	if err := s.requireLogin(); err != nil {
		return err
	}
	chatJID, err := types.ParseJID(args.ChatJID)
	if err != nil {
		return fmt.Errorf("invalid chat JID: %w", err)
	}
	if chatJID.Server != types.GroupServer {
		return fmt.Errorf("chat JID is not a group: %s", args.ChatJID)
	}

	ctx := context.Background()
	info, err := s.client.GetGroupInfo(ctx, chatJID)
	if err != nil {
		return err
	}

	participants := make([]GroupParticipant, 0, len(info.Participants))
	for _, participant := range info.Participants {
		participants = append(participants, GroupParticipant{
			JID:            s.client.ResolveJID(ctx, participant.JID).String(),
			PhoneNumberJID: participant.PhoneNumber.String(),
			LIDJID:         participant.LID.String(),
			DisplayName:    participant.DisplayName,
			IsAdmin:        participant.IsAdmin,
			IsSuperAdmin:   participant.IsSuperAdmin,
		})
	}

	sort.Slice(participants, func(i, j int) bool {
		return participants[i].JID < participants[j].JID
	})

	reply.Participants = participants
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
	if err := s.requireLogin(); err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	reply.AvatarPath = s.syncer.ForceSync(ctx, args.JID)
	return nil
}

// SendPresence types

type SendPresenceArgs struct {
	Available bool
}

func (s *Service) SendPresence(args *SendPresenceArgs, reply *struct{}) error {
	if err := s.requireLogin(); err != nil {
		return err
	}
	state := types.PresenceUnavailable
	if args.Available {
		state = types.PresenceAvailable
	}
	return s.client.SendPresence(context.Background(), state)
}

// SubscribePresence types

type SubscribePresenceArgs struct {
	JID string
}

func (s *Service) SubscribePresence(args *SubscribePresenceArgs, reply *struct{}) error {
	if err := s.requireLogin(); err != nil {
		return err
	}
	jid, err := types.ParseJID(args.JID)
	if err != nil {
		return fmt.Errorf("invalid JID: %w", err)
	}
	return s.client.SubscribePresence(context.Background(), jid)
}

// ChatSettings types

type GetChatSettingsArgs struct {
	ChatJID string
}

type GetChatSettingsReply struct {
	MutedUntil int64 `json:"MutedUntil"` // unix ms: 0 = not muted, -1 = forever
}

func (s *Service) GetChatSettings(args *GetChatSettingsArgs, reply *GetChatSettingsReply) error {
	if err := s.requireLogin(); err != nil {
		return err
	}
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
	if err := s.requireLogin(); err != nil {
		return err
	}
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
	ChatJID                string
	Type                   string // "text", "image", "video", "audio", "sticker", "document", "contact"
	Text                   string
	FilePath               string
	Caption                string
	DurationSeconds        int
	PTT                    bool
	ReplyToMessageID       string
	ReplyParticipantJID    string
	ReplyQuotedMessageJSON string
	MentionedJIDs          []string
}

type SendMessageReply struct {
	MessageID string
	Timestamp int64
}

type EditMessageArgs struct {
	ChatJID                string
	MessageID              string
	Text                   string
	ReplyToMessageID       string
	ReplyParticipantJID    string
	ReplyQuotedMessageJSON string
}

type EditMessageReply struct {
	MessageID string
	Timestamp int64
}

type DeleteMessageArgs struct {
	ChatJID   string
	MessageID string
}

type DeleteMessageReply struct {
	MessageID string
	Timestamp int64
}

func (s *Service) buildMessageContext(args *SendMessageArgs) (*waE2E.ContextInfo, error) {
	if args.ReplyToMessageID == "" && len(args.MentionedJIDs) == 0 {
		return nil, nil
	}

	ctx := context.Background()
	ctxInfo := &waE2E.ContextInfo{}
	if args.ReplyToMessageID != "" {
		ctxInfo.StanzaID = proto.String(args.ReplyToMessageID)

		participant := args.ReplyParticipantJID
		if participant == "" {
			ownJID := s.client.GetOwnJID()
			if !ownJID.IsEmpty() {
				participant = ownJID.String()
			}
		} else {
			participantJID, err := types.ParseJID(participant)
			if err != nil {
				return nil, fmt.Errorf("invalid reply participant JID: %w", err)
			}
			participant = s.client.ResolveJID(ctx, participantJID).String()
		}
		if participant != "" {
			ctxInfo.Participant = proto.String(participant)
		}

		if args.ReplyQuotedMessageJSON != "" {
			quotedMessage := &waE2E.Message{}
			unmarshal := protojson.UnmarshalOptions{DiscardUnknown: true}
			if err := unmarshal.Unmarshal([]byte(args.ReplyQuotedMessageJSON), quotedMessage); err != nil {
				return nil, fmt.Errorf("unmarshal quoted message: %w", err)
			}
			ctxInfo.QuotedMessage = quotedMessage
		}
	}

	if len(args.MentionedJIDs) > 0 {
		mentionedJIDs := make([]string, 0, len(args.MentionedJIDs))
		for _, mentioned := range args.MentionedJIDs {
			mentioned = strings.TrimSpace(mentioned)
			if mentioned == "" {
				continue
			}
			mentionedJID, err := types.ParseJID(mentioned)
			if err != nil {
				return nil, fmt.Errorf("invalid mentioned JID: %w", err)
			}
			mentionedJIDs = append(mentionedJIDs, s.client.ResolveJID(ctx, mentionedJID).String())
		}
		if len(mentionedJIDs) > 0 {
			ctxInfo.MentionedJID = mentionedJIDs
		}
	}

	if ctxInfo.StanzaID == nil && ctxInfo.Participant == nil && ctxInfo.QuotedMessage == nil && len(ctxInfo.MentionedJID) == 0 {
		return nil, nil
	}

	return ctxInfo, nil
}

func (s *Service) sendImageMessage(args *SendMessageArgs, replyContext *waE2E.ContextInfo) (*waE2E.Message, error) {
	data, err := os.ReadFile(args.FilePath)
	if err != nil {
		return nil, fmt.Errorf("read file: %w", err)
	}

	mimetype := mime.TypeByExtension(filepath.Ext(args.FilePath))
	if mimetype == "" {
		mimetype = "image/jpeg"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	uploadResp, err := s.client.Upload(ctx, data, whatsmeow.MediaImage)
	if err != nil {
		return nil, fmt.Errorf("upload: %w", err)
	}

	thumbnail := generateThumbnail(data)

	msg := &waE2E.Message{
		ImageMessage: &waE2E.ImageMessage{
			Mimetype:      proto.String(mimetype),
			URL:           &uploadResp.URL,
			DirectPath:    &uploadResp.DirectPath,
			MediaKey:      uploadResp.MediaKey,
			FileEncSHA256: uploadResp.FileEncSHA256,
			FileSHA256:    uploadResp.FileSHA256,
			FileLength:    &uploadResp.FileLength,
			ContextInfo:   replyContext,
		},
	}
	if args.Caption != "" {
		msg.ImageMessage.Caption = proto.String(args.Caption)
	}
	if thumbnail != nil {
		msg.ImageMessage.JPEGThumbnail = thumbnail
	}

	return msg, nil
}

func (s *Service) sendVideoMessage(args *SendMessageArgs, replyContext *waE2E.ContextInfo) (*waE2E.Message, error) {
	data, err := os.ReadFile(args.FilePath)
	if err != nil {
		return nil, fmt.Errorf("read file: %w", err)
	}

	mimetype := mime.TypeByExtension(filepath.Ext(args.FilePath))
	if mimetype == "" {
		mimetype = "video/mp4"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	uploadResp, err := s.client.Upload(ctx, data, whatsmeow.MediaVideo)
	if err != nil {
		return nil, fmt.Errorf("upload: %w", err)
	}

	msg := &waE2E.Message{
		VideoMessage: &waE2E.VideoMessage{
			Mimetype:      proto.String(mimetype),
			URL:           &uploadResp.URL,
			DirectPath:    &uploadResp.DirectPath,
			MediaKey:      uploadResp.MediaKey,
			FileEncSHA256: uploadResp.FileEncSHA256,
			FileSHA256:    uploadResp.FileSHA256,
			FileLength:    &uploadResp.FileLength,
			ContextInfo:   replyContext,
		},
	}
	if args.Caption != "" {
		msg.VideoMessage.Caption = proto.String(args.Caption)
	}

	return msg, nil
}

func voiceMessageMimetype(filePath string) (string, error) {
	ext := strings.ToLower(filepath.Ext(filePath))
	switch ext {
	case ".ogg", ".oga":
		return "audio/ogg; codecs=opus", nil
	default:
		return "", fmt.Errorf("unsupported audio format for voice note: %s (expected OGG/Opus .ogg recording)", ext)
	}
}

func (s *Service) sendAudioMessage(args *SendMessageArgs, replyContext *waE2E.ContextInfo) (*waE2E.Message, error) {
	if !args.PTT {
		return nil, fmt.Errorf("only push-to-talk voice notes are supported")
	}

	data, err := os.ReadFile(args.FilePath)
	if err != nil {
		return nil, fmt.Errorf("read file: %w", err)
	}

	mimetype, err := voiceMessageMimetype(args.FilePath)
	if err != nil {
		return nil, err
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	uploadResp, err := s.client.Upload(ctx, data, whatsmeow.MediaAudio)
	if err != nil {
		return nil, fmt.Errorf("upload: %w", err)
	}

	seconds := args.DurationSeconds
	if seconds < 0 {
		seconds = 0
	}

	msg := &waE2E.Message{
		AudioMessage: &waE2E.AudioMessage{
			Mimetype:      proto.String(mimetype),
			URL:           &uploadResp.URL,
			DirectPath:    &uploadResp.DirectPath,
			MediaKey:      uploadResp.MediaKey,
			FileEncSHA256: uploadResp.FileEncSHA256,
			FileSHA256:    uploadResp.FileSHA256,
			FileLength:    &uploadResp.FileLength,
			Seconds:       proto.Uint32(uint32(seconds)),
			PTT:           proto.Bool(true),
			ContextInfo:   replyContext,
		},
	}

	return msg, nil
}

func (s *Service) sendStickerMessage(args *SendMessageArgs, replyContext *waE2E.ContextInfo) (*waE2E.Message, error) {
	data, err := os.ReadFile(args.FilePath)
	if err != nil {
		return nil, fmt.Errorf("read file: %w", err)
	}

	mimetype := mime.TypeByExtension(filepath.Ext(args.FilePath))
	if mimetype == "" {
		mimetype = "image/webp"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	uploadResp, err := s.client.Upload(ctx, data, whatsmeow.MediaImage)
	if err != nil {
		return nil, fmt.Errorf("upload: %w", err)
	}

	msg := &waE2E.Message{
		StickerMessage: &waE2E.StickerMessage{
			Mimetype:      proto.String(mimetype),
			URL:           &uploadResp.URL,
			DirectPath:    &uploadResp.DirectPath,
			MediaKey:      uploadResp.MediaKey,
			FileEncSHA256: uploadResp.FileEncSHA256,
			FileSHA256:    uploadResp.FileSHA256,
			FileLength:    &uploadResp.FileLength,
			ContextInfo:   replyContext,
		},
	}

	return msg, nil
}

func (s *Service) sendContactMessage(args *SendMessageArgs, replyContext *waE2E.ContextInfo) (*waE2E.Message, error) {
	vcard, err := os.ReadFile(args.FilePath)
	if err != nil {
		return nil, fmt.Errorf("read file: %w", err)
	}

	displayName := strings.TrimSpace(args.Text)
	if displayName == "" {
		displayName = strings.TrimSuffix(filepath.Base(args.FilePath), filepath.Ext(args.FilePath))
	}
	if displayName == "" {
		displayName = "Contact"
	}

	return &waE2E.Message{
		ContactMessage: &waE2E.ContactMessage{
			DisplayName: proto.String(displayName),
			Vcard:       proto.String(string(vcard)),
			ContextInfo: replyContext,
		},
	}, nil
}

func buildTextMessage(text string, replyContext *waE2E.ContextInfo) *waE2E.Message {
	if replyContext != nil {
		return &waE2E.Message{
			ExtendedTextMessage: &waE2E.ExtendedTextMessage{
				Text:        proto.String(text),
				ContextInfo: replyContext,
			},
		}
	}

	return &waE2E.Message{
		Conversation: proto.String(text),
	}
}

func (s *Service) SendMessage(args *SendMessageArgs, reply *SendMessageReply) error {
	if err := s.requireLogin(); err != nil {
		return err
	}
	jid, err := types.ParseJID(args.ChatJID)
	if err != nil {
		return fmt.Errorf("invalid chat JID: %w", err)
	}

	replyContext, err := s.buildMessageContext(args)
	if err != nil {
		return fmt.Errorf("message context: %w", err)
	}

	var message *waE2E.Message
	switch args.Type {
	case "text":
		message = buildTextMessage(args.Text, replyContext)
	case "image":
		if args.FilePath == "" {
			return fmt.Errorf("file path required for image message")
		}
		msg, err := s.sendImageMessage(args, replyContext)
		if err != nil {
			return fmt.Errorf("image message: %w", err)
		}
		message = msg
	case "video":
		if args.FilePath == "" {
			return fmt.Errorf("file path required for video message")
		}
		msg, err := s.sendVideoMessage(args, replyContext)
		if err != nil {
			return fmt.Errorf("video message: %w", err)
		}
		message = msg
	case "audio":
		if args.FilePath == "" {
			return fmt.Errorf("file path required for audio message")
		}
		msg, err := s.sendAudioMessage(args, replyContext)
		if err != nil {
			return fmt.Errorf("audio message: %w", err)
		}
		message = msg
	case "sticker":
		if args.FilePath == "" {
			return fmt.Errorf("file path required for sticker message")
		}
		msg, err := s.sendStickerMessage(args, replyContext)
		if err != nil {
			return fmt.Errorf("sticker message: %w", err)
		}
		message = msg
	case "contact":
		if args.FilePath == "" {
			return fmt.Errorf("file path required for contact message")
		}
		msg, err := s.sendContactMessage(args, replyContext)
		if err != nil {
			return fmt.Errorf("contact message: %w", err)
		}
		message = msg
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

func (s *Service) EditMessage(args *EditMessageArgs, reply *EditMessageReply) error {
	if err := s.requireLogin(); err != nil {
		return err
	}
	jid, err := types.ParseJID(args.ChatJID)
	if err != nil {
		return fmt.Errorf("invalid chat JID: %w", err)
	}
	if args.MessageID == "" {
		return fmt.Errorf("message ID required")
	}
	if strings.TrimSpace(args.Text) == "" {
		return fmt.Errorf("message text cannot be empty")
	}

	replyContext, err := s.buildMessageContext(&SendMessageArgs{
		ReplyToMessageID:       args.ReplyToMessageID,
		ReplyParticipantJID:    args.ReplyParticipantJID,
		ReplyQuotedMessageJSON: args.ReplyQuotedMessageJSON,
	})
	if err != nil {
		return fmt.Errorf("message context: %w", err)
	}

	message := s.client.BuildEdit(jid, types.MessageID(args.MessageID), buildTextMessage(args.Text, replyContext))

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

func (s *Service) DeleteMessage(args *DeleteMessageArgs, reply *DeleteMessageReply) error {
	if err := s.requireLogin(); err != nil {
		return err
	}
	jid, err := types.ParseJID(args.ChatJID)
	if err != nil {
		return fmt.Errorf("invalid chat JID: %w", err)
	}
	if args.MessageID == "" {
		return fmt.Errorf("message ID required")
	}

	message := s.client.BuildRevoke(jid, types.EmptyJID, types.MessageID(args.MessageID))

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
	if err := s.requireLogin(); err != nil {
		return err
	}
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

type PairPhoneArgs struct {
	Phone string
}

type PairPhoneReply struct {
	Code string
}

func (s *Service) PairPhone(args *PairPhoneArgs, reply *PairPhoneReply) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	code, err := s.client.PairPhone(ctx, args.Phone)
	if err != nil {
		return fmt.Errorf("pair phone: %w", err)
	}
	reply.Code = code
	return nil
}

type SetNotificationCounterArgs struct {
	Count   int32
	Visible bool
}

func (s *Service) SetNotificationCounter(args *SetNotificationCounterArgs, reply *struct{}) error {
	if s.notifier == nil {
		return nil
	}
	return s.notifier.SetCounter(args.Count, args.Visible)
}

type ClearChatNotificationsArgs struct {
	Tags []string
}

func (s *Service) ClearChatNotifications(args *ClearChatNotificationsArgs, reply *struct{}) error {
	if s.notifier == nil {
		return nil
	}
	return s.notifier.ClearPersistentList(args.Tags)
}
