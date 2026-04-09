package waconn

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/appstate"
	"go.mau.fi/whatsmeow/proto/waCompanionReg"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
	"google.golang.org/protobuf/proto"

	_ "modernc.org/sqlite"
)

type Client struct {
	waCli        *whatsmeow.Client
	container    *sqlstore.Container
	log          *slog.Logger
	disconnectCh chan struct{}
	stopCh       chan string

	recoveryMu       sync.Mutex
	recoveryLastTime map[appstate.WAPatchName]time.Time
}

func New(dbPath string, logger *slog.Logger) (*Client, error) {
	ctx := context.Background()
	waLogger := &slogAdapter{logger: logger}

	store.DeviceProps.RequireFullSync = proto.Bool(true)
	store.DeviceProps.HistorySyncConfig.SupportGroupHistory = proto.Bool(true)
	store.DeviceProps.HistorySyncConfig.SupportCallLogHistory = proto.Bool(true)
	store.DeviceProps.PlatformType = waCompanionReg.DeviceProps_ANDROID_PHONE.Enum()
	store.SetOSInfo("Greenline", [3]uint32{0, 1, 0})

	address := fmt.Sprintf("file:%s?_pragma=foreign_keys(1)&_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)", dbPath)
	container, err := sqlstore.New(ctx, "sqlite", address, waLogger.Sub("sqlstore"))
	if err != nil {
		return nil, fmt.Errorf("waconn: open store: %w", err)
	}

	device, err := container.GetFirstDevice(ctx)
	if err != nil {
		container.Close()
		return nil, fmt.Errorf("waconn: get device: %w", err)
	}

	waCli := whatsmeow.NewClient(device, waLogger.Sub("client"))

	c := &Client{
		waCli:            waCli,
		container:        container,
		log:              logger,
		disconnectCh:     make(chan struct{}, 1),
		stopCh:           make(chan string, 1),
		recoveryLastTime: make(map[appstate.WAPatchName]time.Time),
	}

	waCli.AddEventHandler(c.handleEvent)

	return c, nil
}

func (c *Client) handleEvent(evt interface{}) {
	switch v := evt.(type) {
	case *events.Disconnected:
		select {
		case c.disconnectCh <- struct{}{}:
		default:
		}
	case *events.LoggedOut:
		c.log.Warn("whatsmeow: logged out", "reason", v.Reason.String())
		select {
		case c.stopCh <- fmt.Sprintf("logged out: %s", v.Reason.String()):
		default:
		}
	case *events.StreamReplaced:
		select {
		case c.stopCh <- "stream replaced by another client":
		default:
		}
	case *events.ClientOutdated:
		select {
		case c.stopCh <- "client outdated, update required":
		default:
		}
	case *events.TemporaryBan:
		c.log.Error("whatsmeow: temporary ban",
			"reason", v.Code.String(), "expires_in", v.Expire)
		select {
		case c.stopCh <- fmt.Sprintf("temporary ban: %s (expires in %s)",
			v.Code.String(), v.Expire):
		default:
		}
	case *events.AppStateSyncError:
		if errors.Is(v.Error, appstate.ErrMismatchingLTHash) {
			go c.maybeRecoverAppState(v.Name)
		}
	}
}

func (c *Client) ConnectWithRetry(ctx context.Context, onQR func(code string)) {
	const retryDelay = 5 * time.Second

	for {
		if ctx.Err() != nil {
			return
		}

		select {
		case reason := <-c.stopCh:
			c.log.Error("whatsmeow: permanent disconnect, stopping", "reason", reason)
			return
		default:
		}

		if c.waCli.Store.ID == nil {
			c.log.Info("whatsmeow: device not paired, starting QR flow")

			qrChan, err := c.waCli.GetQRChannel(ctx)
			if err != nil {
				c.log.Error("whatsmeow: get QR channel failed", "error", err)
				if !c.sleepCtx(ctx, retryDelay) {
					return
				}
				continue
			}

			if err := c.waCli.Connect(); err != nil {
				c.log.Error("whatsmeow: connect failed", "error", err)
				if !c.sleepCtx(ctx, retryDelay) {
					return
				}
				continue
			}

			paired := false
			for evt := range qrChan {
				switch evt.Event {
				case whatsmeow.QRChannelEventCode:
					onQR(evt.Code)
				case "success":
					paired = true
				default:
					c.log.Info("whatsmeow: QR event", "event", evt.Event)
				}
			}

			onQR("")

			if !paired {
				c.log.Warn("whatsmeow: QR expired, retrying")
				c.waCli.Disconnect()
				c.drainDisconnect()
				if !c.sleepCtx(ctx, retryDelay) {
					return
				}
				continue
			}

			c.log.Info("whatsmeow: paired successfully, waiting for connection")
			c.drainDisconnect()
			if !c.waCli.WaitForConnection(30 * time.Second) {
				c.log.Warn("whatsmeow: timed out waiting for post-pairing connection")
				continue
			}
			c.drainDisconnect()
			c.log.Info("whatsmeow: connected after pairing")
		} else {
			if c.waCli.IsConnected() {
				c.log.Info("whatsmeow: already connected, skipping connect")
			} else {
				if err := c.waCli.Connect(); err != nil {
					c.log.Error("whatsmeow: connect failed", "error", err)
					if !c.sleepCtx(ctx, retryDelay) {
						return
					}
					continue
				}
				c.log.Info("whatsmeow: connected (already paired)")
			}
		}

		select {
		case <-ctx.Done():
			return
		case reason := <-c.stopCh:
			c.log.Error("whatsmeow: permanent disconnect, stopping", "reason", reason)
			return
		case <-c.disconnectCh:
			c.log.Warn("whatsmeow: disconnected, will reconnect")
			if !c.sleepCtx(ctx, retryDelay) {
				return
			}
		}
	}
}

func (c *Client) drainDisconnect() {
	select {
	case <-c.disconnectCh:
	default:
	}
}

func (c *Client) sleepCtx(ctx context.Context, d time.Duration) bool {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-t.C:
		return true
	}
}

func (c *Client) AddEventHandler(handler func(evt interface{})) {
	c.waCli.AddEventHandler(handler)
}

func (c *Client) Logout(ctx context.Context) error {
	return c.waCli.Logout(ctx)
}

func (c *Client) Disconnect() {
	c.waCli.Disconnect()
	c.container.Close()
}

func (c *Client) IsConnected() bool {
	return c.waCli.IsConnected()
}

func (c *Client) IsLoggedIn() bool {
	return c.waCli.IsLoggedIn()
}

func (c *Client) GetAllContacts(ctx context.Context) (map[types.JID]types.ContactInfo, error) {
	return c.waCli.Store.Contacts.GetAllContacts(ctx)
}

func (c *Client) GetJoinedGroups(ctx context.Context) ([]*types.GroupInfo, error) {
	return c.waCli.GetJoinedGroups(ctx)
}

func (c *Client) MarkRead(ctx context.Context, ids []types.MessageID, timestamp time.Time, chat, sender types.JID) error {
	return c.waCli.MarkRead(ctx, ids, timestamp, chat, sender)
}

func (c *Client) GetProfilePictureInfo(ctx context.Context, jid types.JID, params *whatsmeow.GetProfilePictureParams) (*types.ProfilePictureInfo, error) {
	return c.waCli.GetProfilePictureInfo(ctx, jid, params)
}

func (c *Client) GetPNForLID(ctx context.Context, lid types.JID) (types.JID, error) {
	return c.waCli.Store.LIDs.GetPNForLID(ctx, lid)
}

func (c *Client) DownloadMediaWithPath(ctx context.Context, directPath string, encFileHash, fileHash, mediaKey []byte, fileLength int, mediaType whatsmeow.MediaType, mmsType string) ([]byte, error) {
	return c.waCli.DownloadMediaWithPath(ctx, directPath, encFileHash, fileHash, mediaKey, fileLength, mediaType, mmsType)
}

func (c *Client) Upload(ctx context.Context, plaintext []byte, appInfo whatsmeow.MediaType) (whatsmeow.UploadResponse, error) {
	return c.waCli.Upload(ctx, plaintext, appInfo)
}

func (c *Client) SendMessage(ctx context.Context, to types.JID, message *waE2E.Message) (whatsmeow.SendResponse, error) {
	return c.waCli.SendMessage(ctx, to, message)
}

func (c *Client) SubscribePresence(ctx context.Context, jid types.JID) error {
	return c.waCli.SubscribePresence(ctx, jid)
}

func (c *Client) SendPresence(ctx context.Context, state types.Presence) error {
	return c.waCli.SendPresence(ctx, state)
}

func (c *Client) GetChatSettings(ctx context.Context, chat types.JID) (types.LocalChatSettings, error) {
	if c.waCli.Store.ChatSettings == nil {
		return types.LocalChatSettings{}, nil
	}
	return c.waCli.Store.ChatSettings.GetChatSettings(ctx, chat)
}

func (c *Client) IsMuted(ctx context.Context, chat types.JID) bool {
	settings, err := c.GetChatSettings(ctx, chat)
	if err != nil || !settings.Found {
		return false
	}
	if settings.MutedUntil.Equal(store.MutedForever) {
		return true
	}
	return !settings.MutedUntil.IsZero() && settings.MutedUntil.After(time.Now())
}

func (c *Client) SetMuted(ctx context.Context, chat types.JID, muted bool) error {
	patch := appstate.BuildMute(chat, muted, 0)
	err := c.waCli.SendAppState(ctx, patch)
	if err == nil {
		return nil
	}
	c.log.Warn("SetMuted: first attempt failed, resyncing app state", "error", err)
	if syncErr := c.waCli.FetchAppState(ctx, patch.Type, true, false); syncErr != nil {
		c.log.Error("SetMuted: full resync failed", "error", syncErr)
		return fmt.Errorf("app state conflict and resync failed: %w", syncErr)
	}
	return c.waCli.SendAppState(ctx, patch)
}

const appStateRecoveryCooldown = 5 * time.Minute

func (c *Client) maybeRecoverAppState(name appstate.WAPatchName) {
	c.recoveryMu.Lock()
	if time.Since(c.recoveryLastTime[name]) < appStateRecoveryCooldown {
		c.recoveryMu.Unlock()
		return
	}
	c.recoveryLastTime[name] = time.Now()
	c.recoveryMu.Unlock()

	c.log.Warn("app state LTHash mismatch detected, requesting recovery from primary device", "collection", string(name))

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	recoveryCh := make(chan error, 1)
	handlerID := c.waCli.AddEventHandler(func(evt interface{}) {
		switch v := evt.(type) {
		case *events.AppStateSyncComplete:
			if v.Name == name && v.Recovery {
				recoveryCh <- nil
			}
		case *events.AppStateSyncError:
			if v.Name == name {
				recoveryCh <- v.Error
			}
		}
	})
	defer c.waCli.RemoveEventHandler(handlerID)

	msg := whatsmeow.BuildAppStateRecoveryRequest(name)
	if _, err := c.waCli.SendPeerMessage(ctx, msg); err != nil {
		c.log.Error("app state recovery: failed to send request", "collection", string(name), "error", err)
		return
	}

	select {
	case err := <-recoveryCh:
		if err != nil {
			c.log.Error("app state recovery failed", "collection", string(name), "error", err)
		} else {
			c.log.Info("app state recovery completed", "collection", string(name))
		}
	case <-ctx.Done():
		c.log.Error("app state recovery timed out", "collection", string(name))
	}
}

type slogAdapter struct {
	logger *slog.Logger
}

func (a *slogAdapter) Warnf(msg string, args ...interface{}) {
	a.logger.Warn(fmt.Sprintf(msg, args...))
}
func (a *slogAdapter) Errorf(msg string, args ...interface{}) {
	a.logger.Error(fmt.Sprintf(msg, args...))
}
func (a *slogAdapter) Infof(msg string, args ...interface{}) {
	a.logger.Info(fmt.Sprintf(msg, args...))
}
func (a *slogAdapter) Debugf(msg string, args ...interface{}) {
	a.logger.Debug(fmt.Sprintf(msg, args...))
}
func (a *slogAdapter) Sub(module string) waLog.Logger {
	return &slogAdapter{logger: a.logger.With("module", module)}
}

var _ waLog.Logger = (*slogAdapter)(nil)
