package configstore

import (
	"database/sql"
	"errors"
	"fmt"

	_ "modernc.org/sqlite"
)

type Store struct {
	db *sql.DB
}

func New(dbPath string) (*Store, error) {
	dsn := fmt.Sprintf("file:%s?_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)", dbPath)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("configstore: open: %w", err)
	}

	_, err = db.Exec(`CREATE TABLE IF NOT EXISTS config (
		key TEXT PRIMARY KEY,
		value TEXT NOT NULL
	)`)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("configstore: create table: %w", err)
	}

	return &Store{db: db}, nil
}

func (s *Store) Get(key string) (string, bool, error) {
	var value string
	err := s.db.QueryRow(`SELECT value FROM config WHERE key = ?`, key).Scan(&value)
	if errors.Is(err, sql.ErrNoRows) {
		return "", false, nil
	}
	if err != nil {
		return "", false, fmt.Errorf("configstore: get %q: %w", key, err)
	}
	return value, true, nil
}

func (s *Store) Set(key, value string) error {
	_, err := s.db.Exec(
		`INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
		key, value,
	)
	if err != nil {
		return fmt.Errorf("configstore: set: %w", err)
	}
	return nil
}

func (s *Store) Close() error {
	return s.db.Close()
}
