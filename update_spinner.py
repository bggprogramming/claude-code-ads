#!/usr/bin/env python3
"""
Updates spinnerVerbs in ~/.claude/settings.json with the current ad.
Called by: SessionStart hook (initial ad) and Stop hook (rotates per response).
Logs a 'spinner' impression to SQLite + Supabase.
"""
import json
import os
import random
import re
import sqlite3
import ssl
import sys
import threading
import urllib.request
from pathlib import Path

import certifi
import context     as _ctx
import earnings    as _earnings
import feed        as _feed
import viewability as _view

BASE       = Path(__file__).parent
ADS_FILE   = BASE / "ads.json"   # fallback; _feed.load_ads() is primary
DB_FILE    = BASE / "analytics.db"
CFG_FILE   = BASE / "config.json"
SETTINGS   = Path.home() / ".claude" / "settings.json"
SSL_CTX    = ssl.create_default_context(cafile=certifi.where())

_sid = os.environ.get("TERM_SESSION_ID") or os.environ.get("TMUX_PANE") or str(os.getppid())
SESSION_FILE = Path(f"/tmp/claude-ads-{_sid}.json")
SESSION_CAP  = 3


# ── Helpers (duplicated lean versions to keep this script self-contained) ─────

def load_config():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def session_counts():
    try:
        if SESSION_FILE.exists():
            return json.loads(SESSION_FILE.read_text())
    except Exception:
        pass
    return {}

def increment_session(ad_id):
    counts = session_counts()
    counts[ad_id] = counts.get(ad_id, 0) + 1
    try:
        SESSION_FILE.write_text(json.dumps(counts))
    except Exception:
        pass

def select_ad(ads, context_tags=None):
    counts   = session_counts()
    eligible = [a for a in ads if counts.get(a["id"], 0) < SESSION_CAP]
    return _ctx.weighted_sample(eligible or ads, context_tags)

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
    # Add surface column to existing DBs that predate this schema
    try:
        conn.execute("ALTER TABLE events ADD COLUMN surface TEXT DEFAULT 'unknown'")
    except Exception:
        pass
    conn.commit()

def push_supabase(ad_id, ad_text, event_type, surface, cfg, variant="default"):
    # Route through track-event — earnings computed server-side.
    url     = f"{cfg['supabase_url']}/functions/v1/track-event"
    payload = json.dumps({
        "ad_id":   ad_id,
        "ad_text": ad_text,
        "event":   event_type,
        "surface": surface,
        "user_id": cfg.get("user_id"),
        "variant": variant,
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

def log_impression(ad, surface="spinner", ad_text=None, variant="default"):
    cfg      = load_config()
    log_text = ad_text or ad.get("text", "")

    try:
        conn = sqlite3.connect(DB_FILE)
        init_db(conn)
        conn.execute(
            "INSERT INTO events (ad_id, ad_text, event, surface, user_id, variant) "
            "VALUES (?, ?, 'impression', ?, ?, ?)",
            (ad["id"], log_text, surface, cfg.get("user_id"), variant)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    if cfg.get("supabase_url") and cfg.get("supabase_key"):
        t = threading.Thread(
            target=push_supabase,
            args=(ad["id"], log_text, "impression", surface, cfg, variant),
            daemon=True
        )
        t.start()
        t.join(timeout=4)

    _earnings.track(ad, surface)


# ── Safely patch spinnerVerbs in settings.json ────────────────────────────────

def update_spinner_verbs(ad_text):
    """Read settings.json, replace spinnerVerbs, write back atomically."""
    try:
        raw  = SETTINGS.read_text()
        data = json.loads(raw)
    except Exception:
        return False

    data["spinnerVerbs"] = {
        "mode":  "replace",
        "verbs": [ad_text],
    }

    tmp = SETTINGS.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(SETTINGS)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ads = _feed.load_ads()
    if not ads:
        sys.exit(0)

    # Read hook stdin (available when called from Stop/SessionStart hook)
    hook_data = {}
    try:
        raw = sys.stdin.read(4096)
        if raw.strip():
            hook_data = json.loads(raw)
    except Exception:
        pass

    hook_session_id = hook_data.get("session_id")
    hook_cwd        = hook_data.get("cwd")

    context_tags     = _ctx.get_context(cwd=hook_cwd, session_id=hook_session_id)
    ad               = select_ad(ads, context_tags)
    ad_text, variant = _ctx.select_copy(ad, context_tags)

    # Always refresh the spinner verb; only count an impression when the
    # terminal window is visible (not covered by another window).
    if update_spinner_verbs(ad_text) and _view.is_viewable():
        log_impression(ad, surface="spinner", ad_text=ad_text, variant=variant)
        increment_session(ad["id"])


if __name__ == "__main__":
    main()
