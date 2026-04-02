package avatarsync

import (
	"context"
	"crypto/sha256"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/types"
	"greenline.brennoflavio/daemon/waconn"
)

const (
	syncInterval    = 10 * time.Minute
	requestDelay    = 1 * time.Second
	nopicMaxAge     = 24 * time.Hour
	connectPollWait = 5 * time.Second
)

type Syncer struct {
	client   *waconn.Client
	cacheDir string
	log      *slog.Logger
}

func New(client *waconn.Client, cacheDir string, logger *slog.Logger) *Syncer {
	return &Syncer{
		client:   client,
		cacheDir: filepath.Join(cacheDir, "avatars"),
		log:      logger.With("module", "avatarsync"),
	}
}

func HashJID(jid string) string {
	h := sha256.Sum256([]byte(jid))
	return fmt.Sprintf("%x", h[:])[:16]
}

func AvatarJPGPath(cacheDir, jid string) string {
	return filepath.Join(cacheDir, "avatars", HashJID(jid)+".jpg")
}

var noPicMessages = []string{
	"the user has hidden their profile picture from you",
	"that user or group does not have a profile picture",
}

func isNoPicError(err error) bool {
	msg := err.Error()
	for _, m := range noPicMessages {
		if strings.Contains(msg, m) {
			return true
		}
	}
	return false
}

func (s *Syncer) jpgPath(jid string) string {
	return filepath.Join(s.cacheDir, HashJID(jid)+".jpg")
}

func (s *Syncer) idPath(jid string) string {
	return filepath.Join(s.cacheDir, HashJID(jid)+".id")
}

func (s *Syncer) nopicPath(jid string) string {
	return filepath.Join(s.cacheDir, HashJID(jid)+".nopic")
}

func (s *Syncer) Run(ctx context.Context) {
	for {
		if s.client.IsLoggedIn() {
			break
		}
		if !sleepCtx(ctx, connectPollWait) {
			return
		}
	}

	s.log.Info("starting avatar sync")
	s.syncAll(ctx)

	ticker := time.NewTicker(syncInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if s.client.IsLoggedIn() {
				s.syncAll(ctx)
			}
		}
	}
}

func (s *Syncer) syncAll(ctx context.Context) {
	if err := os.MkdirAll(s.cacheDir, 0700); err != nil {
		s.log.Error("failed to create avatar cache dir", "error", err)
		return
	}

	all, err := s.client.GetAllContacts(ctx)
	if err != nil {
		s.log.Error("failed to get contacts for avatar sync", "error", err)
		return
	}

	s.log.Info("syncing contact avatars", "contacts", len(all))
	for jid := range all {
		if ctx.Err() != nil {
			return
		}
		s.syncOne(ctx, jid)
		sleepCtx(ctx, requestDelay)
	}

	groups, err := s.client.GetJoinedGroups(ctx)
	if err != nil {
		s.log.Error("failed to get groups for avatar sync", "error", err)
	} else {
		s.log.Info("syncing group avatars", "groups", len(groups))
		for _, info := range groups {
			if ctx.Err() != nil {
				return
			}
			s.syncOne(ctx, info.JID)
			sleepCtx(ctx, requestDelay)
		}
	}

	s.log.Info("avatar sync complete")
}

func (s *Syncer) syncOne(ctx context.Context, jid types.JID) {
	jidStr := jid.String()

	if s.hasRecentNopic(jidStr) {
		return
	}

	existingID := s.readIDFile(jidStr)
	if existingID != "" {
		if _, err := os.Stat(s.jpgPath(jidStr)); err == nil {
			return
		}
	}

	pic, err := s.client.GetProfilePictureInfo(ctx, jid, &whatsmeow.GetProfilePictureParams{
		Preview:    true,
		ExistingID: existingID,
	})
	if err != nil {
		if isNoPicError(err) {
			s.writeNopic(jidStr)
		} else {
			s.log.Warn("failed to get profile picture info", "jid", jidStr, "error", err)
		}
		return
	}
	if pic == nil {
		s.writeNopic(jidStr)
		return
	}

	if pic.ID == existingID && existingID != "" {
		return
	}

	if err := s.downloadAvatar(pic.URL, jidStr); err != nil {
		s.log.Error("failed to download avatar", "jid", jidStr, "error", err)
		return
	}

	if pic.ID != "" {
		s.writeIDFile(jidStr, pic.ID)
	}
}

func (s *Syncer) downloadAvatar(url, jid string) error {
	resp, err := http.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	tmp := s.jpgPath(jid) + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}

	if _, err := io.Copy(f, resp.Body); err != nil {
		f.Close()
		os.Remove(tmp)
		return err
	}
	f.Close()

	return os.Rename(tmp, s.jpgPath(jid))
}

func (s *Syncer) hasRecentNopic(jid string) bool {
	info, err := os.Stat(s.nopicPath(jid))
	if err != nil {
		return false
	}
	return time.Since(info.ModTime()) < nopicMaxAge
}

func (s *Syncer) writeNopic(jid string) {
	os.Remove(s.jpgPath(jid))
	os.Remove(s.idPath(jid))
	f, err := os.Create(s.nopicPath(jid))
	if err == nil {
		f.Close()
	}
}

func (s *Syncer) readIDFile(jid string) string {
	data, err := os.ReadFile(s.idPath(jid))
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

func (s *Syncer) writeIDFile(jid, id string) {
	os.Remove(s.nopicPath(jid))
	os.WriteFile(s.idPath(jid), []byte(id), 0600)
}

func (s *Syncer) ForceSync(ctx context.Context, jidStr string) string {
	if err := os.MkdirAll(s.cacheDir, 0700); err != nil {
		s.log.Error("failed to create avatar cache dir", "error", err)
		return ""
	}

	os.Remove(s.jpgPath(jidStr))
	os.Remove(s.idPath(jidStr))
	os.Remove(s.nopicPath(jidStr))

	jid, err := types.ParseJID(jidStr)
	if err != nil {
		s.log.Warn("ForceSync: invalid JID", "jid", jidStr, "error", err)
		return ""
	}

	s.syncOne(ctx, jid)

	path := s.jpgPath(jidStr)
	if _, err := os.Stat(path); err == nil {
		return path
	}
	return ""
}

func sleepCtx(ctx context.Context, d time.Duration) bool {
	t := time.NewTimer(d)
	defer t.Stop()
	select {
	case <-ctx.Done():
		return false
	case <-t.C:
		return true
	}
}
