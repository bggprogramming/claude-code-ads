#!/usr/bin/env python3
"""
Local click-tracking redirect server.
GET /click?ad_id=X&dest=URL → log click → 302 to dest
GET /health                  → 200 ok
"""
import json
import os
import sqlite3
import ssl
import sys
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE     = Path(__file__).parent
DB_FILE  = BASE / "analytics.db"
CFG_FILE = BASE / "config.json"
PID_FILE = BASE / "click_server.pid"
PORT     = 54323

import certifi
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def load_config():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def log_click(ad_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            "INSERT INTO events (ad_id, ad_text, event) VALUES (?, '', 'click')",
            (ad_id,)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    cfg = load_config()
    if cfg.get("supabase_url") and cfg.get("supabase_key"):
        url     = f"{cfg['supabase_url']}/rest/v1/events"
        payload = json.dumps({"ad_id": ad_id, "ad_text": "", "event": "click"}).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "apikey":        cfg["supabase_key"],
            "Authorization": f"Bearer {cfg['supabase_key']}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
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


if __name__ == "__main__":
    PID_FILE.write_text(str(os.getpid()))
    try:
        server = HTTPServer(("127.0.0.1", PORT), ClickHandler)
        server.serve_forever()
    finally:
        PID_FILE.unlink(missing_ok=True)
