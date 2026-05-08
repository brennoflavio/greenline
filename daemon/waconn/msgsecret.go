package waconn

import (
	"context"
	"fmt"
	"strings"

	"go.mau.fi/whatsmeow/proto/waCommon"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	"go.mau.fi/whatsmeow/util/gcmutil"
	"go.mau.fi/whatsmeow/util/hkdfutil"
	"google.golang.org/protobuf/proto"
)

type msgSecretType string

const (
	encSecretEventEdit   msgSecretType = "Event Edit"
	encSecretMessageEdit msgSecretType = "Message Edit"
)

type messageEncryptedSecret interface {
	GetEncIV() []byte
	GetEncPayload() []byte
}

func generateMsgSecretKey(
	modificationType msgSecretType, modificationSender types.JID,
	origMsgID types.MessageID, origMsgSender types.JID, origMsgSecret []byte,
) ([]byte, []byte) {
	origMsgSenderStr := origMsgSender.ToNonAD().String()
	modificationSenderStr := modificationSender.ToNonAD().String()

	useCaseSecret := make([]byte, 0, len(origMsgID)+len(origMsgSenderStr)+len(modificationSenderStr)+len(modificationType))
	useCaseSecret = append(useCaseSecret, origMsgID...)
	useCaseSecret = append(useCaseSecret, origMsgSenderStr...)
	useCaseSecret = append(useCaseSecret, modificationSenderStr...)
	useCaseSecret = append(useCaseSecret, modificationType...)

	secretKey := hkdfutil.SHA256(origMsgSecret, nil, useCaseSecret, 32)
	return secretKey, nil
}

func getOrigSenderFromKey(msg *events.Message, key *waCommon.MessageKey) (types.JID, error) {
	if key.GetFromMe() {
		return msg.Info.Sender, nil
	} else if msg.Info.Chat.Server == types.DefaultUserServer || msg.Info.Chat.Server == types.HiddenUserServer {
		sender, err := types.ParseJID(key.GetRemoteJID())
		if err != nil {
			return types.EmptyJID, fmt.Errorf("failed to parse JID %q of original message sender: %w", key.GetRemoteJID(), err)
		}
		return sender, nil
	}

	sender, err := types.ParseJID(key.GetParticipant())
	if sender.Server != types.DefaultUserServer && sender.Server != types.HiddenUserServer {
		err = fmt.Errorf("unexpected server")
	}
	if err != nil {
		return types.EmptyJID, fmt.Errorf("failed to parse JID %q of original message sender: %w", key.GetParticipant(), err)
	}
	return sender, nil
}

func (c *Client) decryptMsgSecret(
	ctx context.Context,
	msg *events.Message,
	useCase msgSecretType,
	encrypted messageEncryptedSecret,
	origMsgKey *waCommon.MessageKey,
) ([]byte, error) {
	origSender, err := getOrigSenderFromKey(msg, origMsgKey)
	if err != nil {
		return nil, err
	}

	baseEncKey, storedOrigSender, err := c.waCli.Store.MsgSecrets.GetMessageSecret(ctx, msg.Info.Chat, origSender, origMsgKey.GetID())
	if err != nil {
		return nil, fmt.Errorf("failed to get original message secret key: %w", err)
	}
	if baseEncKey == nil {
		return nil, fmt.Errorf("original message secret key not found")
	}

	secretKey, additionalData := generateMsgSecretKey(useCase, msg.Info.Sender, origMsgKey.GetID(), origSender, baseEncKey)
	plaintext, err := gcmutil.Decrypt(secretKey, encrypted.GetEncIV(), encrypted.GetEncPayload(), additionalData)
	if err != nil {
		if origSender != storedOrigSender && strings.Contains(err.Error(), "message authentication failed") {
			secretKey, additionalData = generateMsgSecretKey(useCase, msg.Info.Sender, origMsgKey.GetID(), storedOrigSender, baseEncKey)
			plaintext, err = gcmutil.Decrypt(secretKey, encrypted.GetEncIV(), encrypted.GetEncPayload(), additionalData)
		}
		if err != nil {
			return nil, fmt.Errorf("failed to decrypt secret message: %w", err)
		}
	}

	return plaintext, nil
}

func (c *Client) DecryptSecretEncryptedMessage(ctx context.Context, evt *events.Message) (*waE2E.Message, error) {
	encMessage := evt.Message.GetSecretEncryptedMessage()
	if encMessage == nil {
		return nil, fmt.Errorf("given message isn't a secret encrypted message")
	}

	var secretType msgSecretType
	switch encMessage.GetSecretEncType() {
	case waE2E.SecretEncryptedMessage_EVENT_EDIT:
		secretType = encSecretEventEdit
	case waE2E.SecretEncryptedMessage_MESSAGE_EDIT:
		secretType = encSecretMessageEdit
	default:
		return nil, fmt.Errorf("unsupported secret enc type: %s", encMessage.SecretEncType.String())
	}

	plaintext, err := c.decryptMsgSecret(ctx, evt, secretType, encMessage, encMessage.GetTargetMessageKey())
	if err != nil {
		return nil, err
	}

	var msg waE2E.Message
	if err := proto.Unmarshal(plaintext, &msg); err != nil {
		return nil, fmt.Errorf("failed to decode message protobuf: %w", err)
	}
	if evt.Message.MessageContextInfo != nil && msg.MessageContextInfo == nil {
		msg.MessageContextInfo = evt.Message.MessageContextInfo
	}
	return &msg, nil
}

func normalizeEditedPayload(evt *events.Message, payload *waE2E.Message, fallbackTargetID string) {
	if payload == nil {
		return
	}

	contextSource := payload
	targetID := fallbackTargetID
	evt.RawMessage = payload
	evt.UnwrapRaw()
	evt.IsEdit = true
	if evt.Message.GetProtocolMessage().GetType() == waE2E.ProtocolMessage_MESSAGE_EDIT {
		if key := evt.Message.GetProtocolMessage().GetKey(); key != nil && key.GetID() != "" {
			targetID = key.GetID()
		}
		if edited := evt.Message.GetProtocolMessage().GetEditedMessage(); edited != nil {
			evt.Message = edited
			evt.RawMessage = edited
		}
	}
	if targetID != "" {
		evt.Info.ID = targetID
	}
	if evt.Message != nil && evt.Message.MessageContextInfo == nil && contextSource.MessageContextInfo != nil {
		evt.Message.MessageContextInfo = contextSource.MessageContextInfo
	}
}

func (c *Client) NormalizeSecretEncryptedMessage(ctx context.Context, evt *events.Message) error {
	encMessage := evt.Message.GetSecretEncryptedMessage()
	if encMessage == nil {
		return nil
	}

	decrypted, err := c.DecryptSecretEncryptedMessage(ctx, evt)
	if err != nil {
		return err
	}

	normalizeEditedPayload(evt, decrypted, encMessage.GetTargetMessageKey().GetID())
	return nil
}

func (c *Client) NormalizeMessageEdit(ctx context.Context, evt *events.Message) error {
	if evt == nil || evt.Message == nil {
		return nil
	}
	if evt.Message.GetSecretEncryptedMessage() != nil {
		return c.NormalizeSecretEncryptedMessage(ctx, evt)
	}
	if evt.Message.GetProtocolMessage().GetType() != waE2E.ProtocolMessage_MESSAGE_EDIT {
		return nil
	}

	normalizeEditedPayload(evt, evt.Message, "")
	return nil
}
