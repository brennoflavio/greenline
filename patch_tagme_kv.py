import base64
import json
import sqlite3
from pathlib import Path

KV_DB = "kv.db"
MESSAGE_KEY = "message:5521967338145@s.whatsapp.net:1778344573:DD46BCDC5E8EBE51E0"

with sqlite3.connect(KV_DB) as db:
    row = db.execute("SELECT value FROM kv WHERE key = ?", (MESSAGE_KEY,)).fetchone()
    if not row:
        raise SystemExit(f"Message not found: {MESSAGE_KEY}")

    wrapper = json.loads(row[0])
    msg = wrapper["value"]
    raw = msg["raw"]["Message"]

    hydrated = raw["templateMessage"]["hydratedTemplate"]
    image = hydrated["Title"]["ImageMessage"]

    parts = []
    for field in ("hydratedContentText", "hydratedFooterText"):
        value = (hydrated.get(field) or "").strip()
        if value:
            parts.append(value)
    caption = "\n\n".join(parts)

    button_text = ""
    button_url = ""
    for btn in hydrated.get("hydratedButtons") or []:
        hb = btn.get("HydratedButton") or {}
        ub = hb.get("UrlButton") or {}
        if ub.get("displayText") and ub.get("URL"):
            button_text = ub["displayText"]
            button_url = ub["URL"]
            break

    thumb_b64 = image.get("JPEGThumbnail") or ""
    if thumb_b64:
        thumb_dir = Path("replayed-thumbnails").resolve()
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f'{msg["id"]}.jpg'
        thumb_path.write_bytes(base64.b64decode(thumb_b64))
        msg["thumbnail_path"] = "file://" + str(thumb_path)

    msg["type"] = "image"
    msg["caption"] = caption
    msg["button_text"] = button_text
    msg["button_url"] = button_url
    msg["mimetype"] = image.get("mimetype", "")

    db.execute(
        "UPDATE kv SET value = ? WHERE key = ?",
        (json.dumps(wrapper, ensure_ascii=False), MESSAGE_KEY),
    )
    db.commit()

print("Patched KV entry:", MESSAGE_KEY)
