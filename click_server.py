#!/usr/bin/env python3
"""
Local click-tracking redirect server.
GET /click?ad_id=X&dest=URL → log click → 302 to dest
GET /health                  → 200 ok

Writes a heartbeat file every 60s so external monitors can detect
a silently-dead server without making an HTTP call.
"""
import errno
import json
import os
import signal
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
            "share_level": cfg.get("share_level", 0),
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


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True   # avoid TIME_WAIT bind failures on quick restarts


def _read_pid():
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def _pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _health_ok(timeout=0.6):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _serve():
    """Bind first, then claim the pid/heartbeat files — so a failed start never
    clobbers a healthy instance's files."""
    server = ReusableHTTPServer(("127.0.0.1", PORT), ClickHandler)   # may raise OSError
    pid = os.getpid()
    PID_FILE.write_text(str(pid))
    HEARTBEAT_FILE.write_text(json.dumps({"ts": int(time.time()), "port": PORT, "pid": pid}))
    LOG_FILE.write_text(f"started pid={pid} port={PORT}\n")
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        PID_FILE.unlink(missing_ok=True)
        HEARTBEAT_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        _serve()
        sys.exit(0)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            LOG_FILE.write_text(f"FAILED to start: {e}\n")
            sys.exit(1)

    # Port is busy. If a healthy instance is already serving, we are idempotently
    # done — exit 0 rather than dying silently (the old behaviour).
    if _health_ok():
        LOG_FILE.write_text(f"already running on port {PORT}; nothing to do\n")
        sys.exit(0)

    # Port held by a wedged/stale process — try to reclaim it, then rebind once.
    stale = _read_pid()
    if _pid_alive(stale):
        try:
            os.kill(stale, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(20):                 # wait up to ~2s for it to release the port
            if not _pid_alive(stale):
                break
            time.sleep(0.1)

    try:
        _serve()
        sys.exit(0)
    except OSError as e:
        LOG_FILE.write_text(f"FAILED to bind port {PORT} after reclaim attempt: {e}\n")
        sys.exit(1)
