package notify

import (
	"encoding/json"
	"fmt"

	"github.com/godbus/dbus/v5"
)

const (
	postalService = "com.lomiri.Postal"
	postalIface   = "com.lomiri.Postal"
	maxBodyLen    = 100
)

type Notifier struct {
	conn  *dbus.Conn
	appID string
}

func New(appID string) (*Notifier, error) {
	conn, err := dbus.SessionBus()
	if err != nil {
		return nil, err
	}
	return &Notifier{conn: conn, appID: appID}, nil
}

func (n *Notifier) Post(summary, body, icon string) error {
	if len(body) > maxBodyLen {
		body = body[:maxBodyLen] + "…"
	}
	if icon == "" {
		icon = "message"
	}
	card := map[string]interface{}{
		"summary": summary,
		"popup":   true,
		"persist": true,
		"icon":    icon,
	}
	if body != "" {
		card["body"] = body
	}
	msg := map[string]interface{}{
		"notification": map[string]interface{}{
			"card":    card,
			"sound":   true,
			"vibrate": true,
		},
	}
	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("notify: marshal: %w", err)
	}
	obj := n.conn.Object(postalService, makePath(n.appID))
	return obj.Call(postalIface+".Post", 0, n.appID, string(data)).Err
}

func (n *Notifier) Close() {
	n.conn.Close()
}

func makePath(appID string) dbus.ObjectPath {
	pkg := appID
	for i, c := range appID {
		if c == '_' {
			pkg = appID[:i]
			break
		}
	}
	var path []byte
	path = append(path, "/com/lomiri/Postal/"...)
	for i := 0; i < len(pkg); i++ {
		c := pkg[i]
		switch c {
		case '+', '.', '-', ':', '~', '_':
			path = append(path, fmt.Sprintf("_%02x", c)...)
		default:
			path = append(path, c)
		}
	}
	return dbus.ObjectPath(path)
}
