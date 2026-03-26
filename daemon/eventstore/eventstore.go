package eventstore

import (
	"database/sql"
	"fmt"
	"time"

	_ "modernc.org/sqlite"
)

type Event struct {
	ID        int64  `json:"id"`
	EventType string `json:"event_type"`
	Payload   string `json:"payload"`
	CreatedAt int64  `json:"created_at"`
}

type Store struct {
	db *sql.DB
}

func New(dbPath string) (*Store, error) {
	dsn := fmt.Sprintf("file:%s?_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)", dbPath)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("eventstore: open: %w", err)
	}

	_, err = db.Exec(`CREATE TABLE IF NOT EXISTS events (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		event_type TEXT NOT NULL,
		payload TEXT NOT NULL,
		created_at INTEGER NOT NULL
	)`)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("eventstore: create table: %w", err)
	}

	return &Store{db: db}, nil
}

func (s *Store) Insert(eventType string, payload []byte) error {
	_, err := s.db.Exec(
		`INSERT INTO events (event_type, payload, created_at) VALUES (?, ?, ?)`,
		eventType, string(payload), time.Now().Unix(),
	)
	if err != nil {
		return fmt.Errorf("eventstore: insert: %w", err)
	}
	return nil
}

func (s *Store) List(afterID int64, limit int) ([]Event, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 500 {
		limit = 500
	}
	rows, err := s.db.Query(
		`SELECT id, event_type, payload, created_at FROM events WHERE id > ? ORDER BY id LIMIT ?`,
		afterID, limit,
	)
	if err != nil {
		return nil, fmt.Errorf("eventstore: list: %w", err)
	}
	defer rows.Close()

	var events []Event
	for rows.Next() {
		var e Event
		if err := rows.Scan(&e.ID, &e.EventType, &e.Payload, &e.CreatedAt); err != nil {
			return nil, fmt.Errorf("eventstore: scan: %w", err)
		}
		events = append(events, e)
	}
	return events, rows.Err()
}

func (s *Store) Delete(upToID int64) error {
	_, err := s.db.Exec(`DELETE FROM events WHERE id <= ?`, upToID)
	if err != nil {
		return fmt.Errorf("eventstore: delete: %w", err)
	}
	return nil
}

func (s *Store) Close() error {
	return s.db.Close()
}
