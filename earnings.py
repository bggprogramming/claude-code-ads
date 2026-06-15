#!/usr/bin/env python3
"""
Local earnings tracking and referral milestone detection.
Imported by ad.py and update_spinner.py — keeps state in earnings.json.

Units: millicents (1/1000 of a cent) to avoid float precision issues.
  $5.00  = 500,000 mc  = MILESTONE_MC  (referral unlock trigger)
  $10.00 = 1,000,000 mc = REFERRAL_BONUS_MC  (bonus paid to both parties)

CPM model:
  statusline impression = ad.cpm * 100 millicents  (e.g. $25 CPM → 2500 mc = $0.025/imp)
  spinner impression    = ad.cpm * 50  millicents  (half rate — less prominent)

To earn $5 at $25 CPM statusline: 200 impressions ≈ 1–2 days of active coding.
"""
import json
import ssl
import threading
import urllib.request
from pathlib import Path

import certifi

BASE          = Path(__file__).parent
EARNINGS_FILE = BASE / "earnings.json"
CFG_FILE      = BASE / "config.json"
SSL_CTX       = ssl.create_default_context(cafile=certifi.where())

MILESTONE_MC       = 500_000    # $5.00 — referral unlock trigger
REFERRAL_BONUS_MC  = 1_000_000  # $10.00 — bonus paid to each party


# ── Local state ───────────────────────────────────────────────────────────────

def load_earnings():
    try:
        if EARNINGS_FILE.exists():
            return json.loads(EARNINGS_FILE.read_text())
    except Exception:
        pass
    return {"total_mc": 0, "milestone_hit": False, "imp_statusline": 0, "imp_spinner": 0}


def save_earnings(state):
    try:
        tmp = EARNINGS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(EARNINGS_FILE)
    except Exception:
        pass


# ── Earnings per impression ───────────────────────────────────────────────────

def impression_mc(ad, surface):
    """Millicents earned for one impression of this ad on this surface."""
    cpm = ad.get("cpm", 20)
    if surface == "statusline":
        return cpm * 100
    return cpm * 50   # spinner = half rate


# ── Supabase calls ────────────────────────────────────────────────────────────

def load_config():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _push_milestone(cfg, referral_code, referred_by):
    """Mark milestone on user record and insert referral bonus row."""
    url_base = cfg["supabase_url"]
    headers  = {
        "apikey":        cfg["supabase_key"],
        "Authorization": f"Bearer {cfg['supabase_key']}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }

    # Mark user milestone
    patch_url = f"{url_base}/rest/v1/users?id=eq.{cfg['user_id']}"
    req = urllib.request.Request(
        patch_url,
        data=json.dumps({"milestone_hit": True}).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=4, context=SSL_CTX)
    except Exception:
        pass

    # $10/$10 — insert bonus for referrer AND for the newly-milestoned user
    if referred_by:
        bonus_url = f"{url_base}/rest/v1/referral_bonuses"

        bonuses = [
            # referrer gets $10
            {"referrer_code": referred_by,    "referred_code": referral_code, "amount_millicents": REFERRAL_BONUS_MC, "recipient": "referrer"},
            # referred user also gets $10
            {"referrer_code": referred_by,    "referred_code": referral_code, "amount_millicents": REFERRAL_BONUS_MC, "recipient": "referred"},
        ]
        for b in bonuses:
            req = urllib.request.Request(
                bonus_url,
                data=json.dumps(b).encode(),
                headers=headers,
                method="POST",
            )
            try:
                urllib.request.urlopen(req, timeout=4, context=SSL_CTX)
            except Exception:
                pass


# ── Public API ────────────────────────────────────────────────────────────────

def track(ad, surface):
    """
    Record earnings for one impression. Call after logging the impression.
    If this impression crosses the $5 milestone for the first time, fires
    the referral bonus in a background thread.
    Returns (total_dollars: float, milestone_just_hit: bool).
    """
    cfg   = load_config()
    state = load_earnings()

    mc          = impression_mc(ad, surface)
    state["total_mc"] += mc
    key = f"imp_{surface}"
    state[key]  = state.get(key, 0) + 1

    milestone_just_hit = False
    if not state["milestone_hit"] and state["total_mc"] >= MILESTONE_MC:
        state["milestone_hit"] = True
        milestone_just_hit     = True

    save_earnings(state)

    # Fire Supabase update in background — non-blocking
    if milestone_just_hit and cfg.get("user_id") and cfg.get("supabase_url"):
        t = threading.Thread(
            target=_push_milestone,
            args=(cfg, cfg.get("referral_code", ""), cfg.get("referred_by", "")),
            daemon=True,
        )
        t.start()
        t.join(timeout=4)

    return state["total_mc"] / 100_000, milestone_just_hit   # return dollars


def total_dollars():
    return load_earnings()["total_mc"] / 100_000
