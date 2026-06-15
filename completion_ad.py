#!/usr/bin/env python3
"""
PostToolUse hook — prints a premium "completion" ad after long-running tools.

Fires when a tool took >30s to complete (measured by record_tool_start.py).
Format: a dim separator line that appears in terminal scrollback after the response:

  ──── Sponsored by Cursor · AI pair programmer that actually ships · cursor.com ────

Charges 2× the statusline rate ($50 CPM at $25 base) — high-attention placement.
"""
import json
import os
import sqlite3
import ssl
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE             = Path(__file__).parent
DB_FILE          = BASE / "analytics.db"
CFG_FILE         = BASE / "config.json"
THRESHOLD        = 30    # seconds — minimum tool duration to show completion ad
WIDTH            = 78    # line width for separator
_TOOL_START_DIR  = "/tmp"

sys.path.insert(0, str(BASE))
import certifi
import context     as _ctx
import earnings    as _earnings
import feed        as _feed
import viewability as _view

SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def load_config():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def elapsed_since_tool_start(session_id):
    """Return seconds since the current tool started, or None if unknown."""
    safe_sid  = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(session_id))
    tool_file = Path(_TOOL_START_DIR) / f"claude-ads-tool-start-{safe_sid}.json"
    try:
        data = json.loads(tool_file.read_text())
        return time.time() - data.get("ts", time.time())
    except Exception:
        return None


def format_completion_line(ad):
    """Format the sponsored separator line to exactly WIDTH chars."""
    raw = ad.get("completion_text") or _derive_completion(ad)
    # Center it with ─ padding
    inner = f" {raw.strip('─').strip()} "
    pad   = max(0, WIDTH - len(inner))
    left  = pad // 2
    right = pad - left
    return "─" * left + inner + "─" * right


def _derive_completion(ad):
    """Fallback: build completion text from ad text."""
    import re
    text    = ad.get("text", "")
    company = re.match(r'^[✦⚡◆▸]\s*(\w+)', text)
    company = company.group(1) if company else "Sponsor"
    domain  = re.search(r'(\w[\w-]*\.(?:com|io|dev|app|ai|co|net|sh)[\S]*)\s*$', text)
    domain  = domain.group(1) if domain else ad.get("url", "")
    return f"Sponsored by {company} · {domain}"


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
    for col, dflt in [("surface", "'unknown'"), ("user_id", "NULL"), ("variant", "'default'")]:
        try:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} TEXT DEFAULT {dflt}")
        except Exception:
            pass
    conn.commit()


def push_supabase(ad_id, ad_text, cfg, variant):
    # Route through track-event — earnings computed server-side.
    url     = f"{cfg['supabase_url']}/functions/v1/track-event"
    payload = json.dumps({
        "ad_id":   ad_id,
        "ad_text": ad_text,
        "event":   "impression",
        "surface": "completion",
        "user_id": cfg.get("user_id"),
        "variant": variant,
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


def log_impression(ad, variant, cfg):
    try:
        conn = sqlite3.connect(DB_FILE)
        init_db(conn)
        conn.execute(
            "INSERT INTO events (ad_id, ad_text, event, surface, user_id, variant) "
            "VALUES (?, ?, 'impression', 'completion', ?, ?)",
            (ad["id"], ad.get("text", ""), cfg.get("user_id"), variant)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    if cfg.get("supabase_url") and cfg.get("supabase_key"):
        threading.Thread(target=push_supabase, args=(ad["id"], ad.get("text", ""), cfg, variant), daemon=True).start()

    _earnings.track(ad, "completion")


def main():
    # Read PostToolUse hook stdin
    data = {}
    try:
        raw = sys.stdin.read(4096)
        if raw.strip():
            data = json.loads(raw)
    except Exception:
        pass

    session_id = data.get("session_id") or os.environ.get("TERM_SESSION_ID") or "unknown"

    # Only fire if the tool ran for >THRESHOLD seconds
    elapsed = elapsed_since_tool_start(session_id)
    if elapsed is None or elapsed < THRESHOLD:
        sys.exit(0)

    # Select ad and format completion line
    ads = _feed.load_ads()
    if not ads:
        sys.exit(0)

    cfg          = load_config()
    hook_cwd     = data.get("cwd")
    context_tags = _ctx.get_context(cwd=hook_cwd, session_id=session_id)
    ad           = _ctx.weighted_sample(ads, context_tags)
    ad_text, variant = _ctx.select_copy(ad, context_tags)

    line = format_completion_line(ad)

    # Print dim separator to /dev/tty so it lands in scrollback
    output = f"\033[2m{line}\033[0m\n"
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(output)
            tty.flush()
    except Exception:
        try:
            sys.stdout.write(output)
            sys.stdout.flush()
        except Exception:
            pass

    # Count only when the terminal window is visible (not covered).
    if _view.is_viewable():
        log_impression(ad, variant, cfg)


if __name__ == "__main__":
    main()
