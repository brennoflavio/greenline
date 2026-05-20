package notify

import (
	"fmt"

	"github.com/godbus/dbus/v5"
)

const (
	postalService = "com.lomiri.Postal"
	postalIface   = "com.lomiri.Postal"
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

func (n *Notifier) Post(payload []byte) error {
	obj := n.conn.Object(postalService, makePath(n.appID))
	return obj.Call(postalIface+".Post", 0, n.appID, string(payload)).Err
}

func (n *Notifier) SetCounter(count int32, visible bool) error {
	obj := n.conn.Object(postalService, makePath(n.appID))
	return obj.Call(postalIface+".SetCounter", 0, n.appID, count, visible).Err
}

func (n *Notifier) ClearPersistentList(tags []string) error {
	if len(tags) == 0 {
		return nil
	}
	obj := n.conn.Object(postalService, makePath(n.appID))
	return obj.Call(postalIface+".ClearPersistentList", 0, n.appID, tags).Err
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
