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
	"sort"
	"strings"
	"sync"
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

type queuePriority int

const (
	priorityLow queuePriority = iota
	priorityHigh
	priorityUrgent
)

type queueItem struct {
	jid      types.JID
	priority queuePriority
	force    bool
	revision uint64
}

type Event struct {
	JID        string `json:"JID"`
	AvatarPath string `json:"AvatarPath,omitempty"`
	Remove     bool   `json:"Remove"`
}

type Syncer struct {
	client   *waconn.Client
	cacheDir string
	log      *slog.Logger
	onChange func(Event)

	mu        sync.Mutex
	queued    map[string]*queueItem
	queues    [3][]string
	revisions map[string]uint64
	wakeCh    chan struct{}
}

func New(client *waconn.Client, cacheDir string, logger *slog.Logger, onChange func(Event)) *Syncer {
	return &Syncer{
		client:    client,
		cacheDir:  filepath.Join(cacheDir, "avatars"),
		log:       logger.With("module", "avatarsync"),
		onChange:  onChange,
		queued:    make(map[string]*queueItem),
		revisions: make(map[string]uint64),
		wakeCh:    make(chan struct{}, 1),
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

	if err := os.MkdirAll(s.cacheDir, 0700); err != nil {
		s.log.Error("failed to create avatar cache dir", "error", err)
		return
	}

	s.log.Info("starting avatar sync")
	s.seedLowPriority(ctx)

	ticker := time.NewTicker(syncInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if s.client.IsLoggedIn() {
				s.seedLowPriority(ctx)
			}
		default:
		}

		job, ok := s.nextJob()
		if !ok {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				if s.client.IsLoggedIn() {
					s.seedLowPriority(ctx)
				}
			case <-s.wakeCh:
			}
			continue
		}

		change := s.syncOne(ctx, job.jid, job.force)
		if s.isCurrentRevision(job.jid.String(), job.revision) {
			s.emitChange(change)
		} else {
			s.discardStaleChange(job.jid.String(), change)
		}
		if !sleepCtx(ctx, requestDelay) {
			return
		}
	}
}

func (s *Syncer) seedLowPriority(ctx context.Context) {
	contactJIDs, err := s.contactJIDs(ctx)
	if err != nil {
		s.log.Error("failed to get contacts for avatar sync", "error", err)
		return
	}
	s.enqueueBatch(contactJIDs, priorityLow, false)

	groupJIDs, err := s.groupJIDs(ctx)
	if err != nil {
		s.log.Error("failed to get groups for avatar sync", "error", err)
		return
	}
	s.enqueueBatch(groupJIDs, priorityLow, false)

	s.log.Info("seeded avatar sync queue", "contacts", len(contactJIDs), "groups", len(groupJIDs))
}

func (s *Syncer) contactJIDs(ctx context.Context) ([]types.JID, error) {
	all, err := s.client.GetAllContacts(ctx)
	if err != nil {
		return nil, err
	}

	jids := make([]types.JID, 0, len(all))
	for jid := range all {
		jids = append(jids, jid)
	}
	sort.Slice(jids, func(i, j int) bool {
		return jids[i].String() < jids[j].String()
	})
	return jids, nil
}

func (s *Syncer) groupJIDs(ctx context.Context) ([]types.JID, error) {
	groups, err := s.client.GetJoinedGroups(ctx)
	if err != nil {
		return nil, err
	}

	jids := make([]types.JID, 0, len(groups))
	for _, info := range groups {
		jids = append(jids, info.JID)
	}
	sort.Slice(jids, func(i, j int) bool {
		return jids[i].String() < jids[j].String()
	})
	return jids, nil
}

func (s *Syncer) PromoteHigh(jidStrs []string) {
	jids := make([]types.JID, 0, len(jidStrs))
	for _, jidStr := range jidStrs {
		jid, err := types.ParseJID(jidStr)
		if err != nil {
			s.log.Warn("invalid avatar priority JID", "jid", jidStr, "error", err)
			continue
		}
		jids = append(jids, jid)
	}
	s.enqueueBatch(jids, priorityHigh, false)
}

func (s *Syncer) PromoteUrgent(jidStr string) {
	jid, err := types.ParseJID(jidStr)
	if err != nil {
		s.log.Warn("invalid urgent avatar JID", "jid", jidStr, "error", err)
		return
	}
	s.enqueueBatch([]types.JID{jid}, priorityUrgent, true)
}

func (s *Syncer) Remove(jidStr string) {
	if err := os.MkdirAll(s.cacheDir, 0700); err != nil {
		s.log.Error("failed to create avatar cache dir", "error", err)
		return
	}

	s.mu.Lock()
	s.bumpRevisionLocked(jidStr)
	s.mu.Unlock()

	if s.clearAvatar(jidStr) {
		s.emitChange(&Event{JID: jidStr, Remove: true})
	}
}

func (s *Syncer) enqueueBatch(jids []types.JID, priority queuePriority, force bool) {
	if len(jids) == 0 {
		return
	}

	changed := false
	s.mu.Lock()
	for _, jid := range jids {
		if s.enqueueLocked(jid, priority, force) {
			changed = true
		}
	}
	s.mu.Unlock()

	if changed {
		s.signalWorker()
	}
}

func (s *Syncer) enqueueLocked(jid types.JID, priority queuePriority, force bool) bool {
	jidStr := jid.String()
	if jidStr == "" {
		return false
	}

	revision := s.revisions[jidStr]
	if force {
		revision = s.bumpRevisionLocked(jidStr)
	}

	item, ok := s.queued[jidStr]
	if ok {
		changed := false
		if priority > item.priority {
			item.priority = priority
			s.queues[priority] = append(s.queues[priority], jidStr)
			changed = true
		}
		if force {
			if !item.force {
				item.force = true
				changed = true
			}
			if item.revision != revision {
				item.revision = revision
				changed = true
			}
		}
		return changed
	}

	s.queued[jidStr] = &queueItem{jid: jid, priority: priority, force: force, revision: revision}
	s.queues[priority] = append(s.queues[priority], jidStr)
	return true
}

func (s *Syncer) nextJob() (*queueItem, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()

	for priority := int(priorityUrgent); priority >= int(priorityLow); priority-- {
		for len(s.queues[priority]) > 0 {
			jidStr := s.queues[priority][0]
			s.queues[priority] = s.queues[priority][1:]

			item := s.queued[jidStr]
			if item == nil {
				continue
			}
			if int(item.priority) != priority {
				continue
			}

			delete(s.queued, jidStr)
			job := *item
			return &job, true
		}
	}

	return nil, false
}

func (s *Syncer) syncOne(ctx context.Context, jid types.JID, forceRefresh bool) *Event {
	jidStr := jid.String()
	jpgPath := s.jpgPath(jidStr)
	_, jpgErr := os.Stat(jpgPath)
	hasJPG := jpgErr == nil

	if s.hasRecentNopic(jidStr) && !forceRefresh {
		return nil
	}

	existingID := s.readIDFile(jidStr)
	pic, err := s.getProfilePictureInfo(ctx, jid, existingID, forceRefresh)
	if err != nil {
		if isNoPicError(err) {
			if s.clearAvatar(jidStr) {
				return &Event{JID: jidStr, Remove: true}
			}
		} else {
			s.log.Warn("failed to get profile picture info", "jid", jidStr, "error", err)
		}
		return nil
	}
	if pic == nil {
		if existingID != "" {
			if hasJPG {
				return nil
			}
			pic, err = s.getProfilePictureInfo(ctx, jid, "", false)
			if err != nil {
				if isNoPicError(err) {
					if s.clearAvatar(jidStr) {
						return &Event{JID: jidStr, Remove: true}
					}
				} else {
					s.log.Warn("failed to refresh missing avatar file", "jid", jidStr, "error", err)
				}
				return nil
			}
			if pic == nil {
				return nil
			}
		} else {
			if s.clearAvatar(jidStr) {
				return &Event{JID: jidStr, Remove: true}
			}
			return nil
		}
	}

	if pic.ID == existingID && existingID != "" && hasJPG {
		return nil
	}

	if err := s.downloadAvatar(ctx, pic.URL, jidStr); err != nil {
		s.log.Error("failed to download avatar", "jid", jidStr, "error", err)
		return nil
	}

	if pic.ID != "" {
		s.writeIDFile(jidStr, pic.ID)
	}

	return &Event{JID: jidStr, AvatarPath: jpgPath}
}

func (s *Syncer) getProfilePictureInfo(
	ctx context.Context,
	jid types.JID,
	existingID string,
	forceRefresh bool,
) (*types.ProfilePictureInfo, error) {
	params := &whatsmeow.GetProfilePictureParams{Preview: true}
	if !forceRefresh {
		params.ExistingID = existingID
	}
	return s.client.GetProfilePictureInfo(ctx, jid, params)
}

func (s *Syncer) clearAvatar(jid string) bool {
	removedJPG := removeIfExists(s.jpgPath(jid))
	removedID := removeIfExists(s.idPath(jid))

	nopicCreated := false
	if _, err := os.Stat(s.nopicPath(jid)); os.IsNotExist(err) {
		nopicCreated = true
	}
	f, err := os.Create(s.nopicPath(jid))
	if err == nil {
		f.Close()
	}

	return removedJPG || removedID || nopicCreated
}

func removeIfExists(path string) bool {
	err := os.Remove(path)
	return err == nil
}

func (s *Syncer) downloadAvatar(ctx context.Context, url, jid string) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}

	resp, err := http.DefaultClient.Do(req)
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
	if err := f.Close(); err != nil {
		os.Remove(tmp)
		return err
	}

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

func (s *Syncer) emitChange(change *Event) {
	if change == nil || s.onChange == nil {
		return
	}
	s.onChange(*change)
}

func (s *Syncer) isCurrentRevision(jid string, revision uint64) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.revisions[jid] == revision
}

func (s *Syncer) discardStaleChange(jid string, change *Event) {
	if change == nil || change.Remove {
		return
	}
	removeIfExists(s.jpgPath(jid))
	removeIfExists(s.idPath(jid))
}

func (s *Syncer) bumpRevisionLocked(jid string) uint64 {
	s.revisions[jid]++
	return s.revisions[jid]
}

func (s *Syncer) signalWorker() {
	select {
	case s.wakeCh <- struct{}{}:
	default:
	}
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
