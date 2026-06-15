#!/usr/bin/env python3
"""
Local click-tracking redirect server.
GET /click?ad_id=X&dest=URL → log click → 302 to dest
GET /health                  → 200 ok

Writes a heartbeat file every 60s so external monitors can detect
a silently-dead server without making an HTTP call.
"""
import json
import os
import sqlite3
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE           = Path(__file__).parent
DB_FILE        = BASE / "analytics.db"
CFG_FILE       = BASE / "config.json"
PID_FILE       = BASE / "click_server.pid"
LOG_FILE       = BASE / "click_server.log"
HEARTBEAT_FILE = Path("/tmp/claude-ads-server-heartbeat.json")
PORT           = 54323

import certifi
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def load_config():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id    TEXT NOT NULL,
            ad_text  TEXT NOT NULL,
            event    TEXT NOT NULL CHECK(event IN ('impression','click')),
            surface  TEXT DEFAULT 'unknown',
            ts       TEXT DEFAULT (datetime('now'))
        )
    """)
    try:
        conn.execute("ALTER TABLE events ADD COLUMN surface TEXT DEFAULT 'unknown'")
    except Exception:
        pass
    conn.commit()

def log_click(ad_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        init_db(conn)
        conn.execute(
            "INSERT INTO events (ad_id, ad_text, event, surface) VALUES (?, '', 'click', 'click')",
            (ad_id,)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    cfg = load_config()
    if cfg.get("supabase_url") and cfg.get("supabase_key"):
        # Route through track-event (anon INSERT on events is revoked).
        url     = f"{cfg['supabase_url']}/functions/v1/track-event"
        payload = json.dumps({
            "ad_id":   ad_id,
            "ad_text": "",
            "event":   "click",
            "surface": "click",
            "user_id": cfg.get("user_id"),
        }).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "apikey":        cfg["supabase_key"],
            "Authorization": f"Bearer {cfg['supabase_key']}",
            "Content-Type":  "application/json",
        }, method="POST")
        try:
            urllib.request.urlopen(req, timeout=4, context=SSL_CTX)
        except Exception:
            pass


class ClickHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence request logs

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/click":
            ad_id = params.get("ad_id", ["unknown"])[0]
            dest  = params.get("dest",  ["https://example.com"])[0]
            threading.Thread(target=log_click, args=(ad_id,), daemon=True).start()
            self.send_response(302)
            self.send_header("Location", dest)
            self.end_headers()

        elif parsed.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        else:
            self.send_response(404)
            self.end_headers()


def _heartbeat_loop():
    """Write a liveness timestamp every 60s so the health-check script can
    detect a silently-dead server without an HTTP round-trip."""
    pid = os.getpid()
    while True:
        try:
            HEARTBEAT_FILE.write_text(json.dumps({
                "ts":   int(time.time()),
                "port": PORT,
                "pid":  pid,
            }))
        except Exception:
            pass
        time.sleep(60)


if __name__ == "__main__":
    pid = os.getpid()
    PID_FILE.write_text(str(pid))

    # Start heartbeat background thread
    threading.Thread(target=_heartbeat_loop, daemon=True).start()

    try:
        server = HTTPServer(("127.0.0.1", PORT), ClickHandler)
        LOG_FILE.write_text(f"started pid={pid} port={PORT}\n")
        HEARTBEAT_FILE.write_text(json.dumps({"ts": int(time.time()), "port": PORT, "pid": pid}))
        server.serve_forever()
    except OSError as e:
        LOG_FILE.write_text(f"FAILED to bind port {PORT}: {e}\n")
        sys.exit(1)
    finally:
        PID_FILE.unlink(missing_ok=True)
        HEARTBEAT_FILE.unlink(missing_ok=True)
