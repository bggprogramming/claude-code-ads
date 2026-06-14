#!/usr/bin/env python3
"""
Claude Code statusLine ad server.
Features: OSC 8 clickable links, contextual targeting, session frequency capping,
          dual-write to SQLite + Supabase.
"""
import json
import os
import random
import sqlite3
import ssl
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import certifi

BASE      = Path(__file__).parent
ADS_FILE  = BASE / "ads.json"
DB_FILE   = BASE / "analytics.db"
CFG_FILE  = BASE / "config.json"
SSL_CTX   = ssl.create_default_context(cafile=certifi.where())
CLICK_PORT = 54323
SESSION_CAP = 3  # max impressions per ad per terminal session

# Session file keyed by PID of the shell so each new terminal = new session
_sid = os.environ.get("TERM_SESSION_ID") or os.environ.get("TMUX_PANE") or str(os.getppid())
SESSION_FILE = Path(f"/tmp/claude-ads-{_sid}.json")


# ── Config ────────────────────────────────────────────────────────────────────

def load_config():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Context detection ─────────────────────────────────────────────────────────

CONTEXT_CHECKS = {
    "javascript": ["package.json", "node_modules", ".eslintrc.js", ".eslintrc.json"],
    "typescript": ["tsconfig.json"],
    "python":     ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    "rust":       ["Cargo.toml"],
    "go":         ["go.mod"],
    "docker":     ["docker-compose.yml", "docker-compose.yaml", "Dockerfile"],
    "infra":      [".terraform", "serverless.yml", "pulumi.yaml", "cdk.json"],
    "database":   [".env"],  # broad signal — refined by ad tags
}

def detect_context():
    cwd = Path.cwd()
    tags = set()
    for tag, files in CONTEXT_CHECKS.items():
        if any((cwd / f).exists() for f in files):
            tags.add(tag)
    return tags


# ── Session frequency cap ─────────────────────────────────────────────────────

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
    return counts[ad_id]


# ── Ad selection ──────────────────────────────────────────────────────────────

def weighted_sample(pool):
    total = sum(a.get("weight", 1) for a in pool)
    r = random.random() * total
    for ad in pool:
        r -= ad.get("weight", 1)
        if r <= 0:
            return ad
    return pool[-1]

def select_ad(ads, context_tags):
    counts = session_counts()

    # Eligible: under cap AND (no tags on ad, or tags overlap context)
    eligible = [
        a for a in ads
        if counts.get(a["id"], 0) < SESSION_CAP
        and (not a.get("tags") or not context_tags or context_tags & set(a.get("tags", [])))
    ]

    # If everything is capped or nothing matches context, open up to all
    if not eligible:
        eligible = [a for a in ads if counts.get(a["id"], 0) < SESSION_CAP] or ads

    return weighted_sample(eligible)


# ── Analytics ─────────────────────────────────────────────────────────────────

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

def push_supabase(ad_id, ad_text, event_type, surface, cfg):
    url     = f"{cfg['supabase_url']}/rest/v1/events"
    payload = json.dumps({
        "ad_id":   ad_id,
        "ad_text": ad_text,
        "event":   event_type,
        "surface": surface,
    }).encode()
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

def log_impression(ad, cfg, surface="statusline"):
    try:
        conn = sqlite3.connect(DB_FILE)
        init_db(conn)
        conn.execute(
            "INSERT INTO events (ad_id, ad_text, event, surface) VALUES (?, ?, 'impression', ?)",
            (ad["id"], ad["text"], surface)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    if cfg.get("supabase_url") and cfg.get("supabase_key"):
        t = threading.Thread(
            target=push_supabase,
            args=(ad["id"], ad["text"], "impression", surface, cfg),
            daemon=True
        )
        t.start()
        t.join(timeout=4)


# ── OSC 8 clickable link ──────────────────────────────────────────────────────

def make_clickable(text, ad_id, dest_url):
    encoded   = urllib.parse.quote(dest_url, safe="")
    track_url = f"http://127.0.0.1:{CLICK_PORT}/click?ad_id={ad_id}&dest={encoded}"
    return f"\033]8;;{track_url}\033\\{text}\033]8;;\033\\"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        with open(ADS_FILE) as f:
            ads = json.load(f)
    except Exception:
        sys.exit(0)

    if not ads:
        sys.exit(0)

    cfg          = load_config()
    context_tags = detect_context()
    ad           = select_ad(ads, context_tags)

    log_impression(ad, cfg)
    increment_session(ad["id"])

    print(make_clickable(ad["text"], ad["id"], ad["url"]))


if __name__ == "__main__":
    main()
