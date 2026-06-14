#!/usr/bin/env python3
"""
Referral dashboard — run directly to see your referral link, earnings progress,
and the status of people you've referred.

  python3 ~/.claude/ads/referral.py
"""
import json
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi

BASE     = Path(__file__).parent
CFG_FILE = BASE / "config.json"
SSL_CTX  = ssl.create_default_context(cafile=certifi.where())

MILESTONE_MC     = 500_000   # $5.00 in millicents
BONUS_DOLLARS    = 5.00


def load_config():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def load_earnings():
    ef = BASE / "earnings.json"
    try:
        if ef.exists():
            return json.loads(ef.read_text())
    except Exception:
        pass
    return {"total_mc": 0, "milestone_hit": False}


def fetch(cfg, path):
    url = f"{cfg['supabase_url']}/rest/v1/{path}"
    req = urllib.request.Request(url, headers={
        "apikey":        cfg["supabase_key"],
        "Authorization": f"Bearer {cfg['supabase_key']}",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=5, context=SSL_CTX)
        return json.loads(resp.read())
    except Exception:
        return []


def bar(value, total, width=24):
    filled = min(int(value / max(total, 1) * width), width)
    return "█" * filled + "░" * (width - filled)


def main():
    cfg = load_config()
    if not cfg.get("user_id"):
        print("  Not set up yet. Run: python3 ~/.claude/ads/setup.py")
        sys.exit(0)

    earnings = load_earnings()
    total_mc  = earnings.get("total_mc", 0)
    earned    = total_mc / 100_000   # dollars
    code      = cfg.get("referral_code", "????")

    print()
    print("╔══════════════════════════════════════════════╗")
    print("║           Referral Dashboard                 ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    # ── Your earnings progress ────────────────────────────────────────────────
    progress = min(total_mc / MILESTONE_MC, 1.0)
    pct      = int(progress * 100)
    b        = bar(total_mc, MILESTONE_MC)

    print(f"  Your earnings:  ${earned:.4f} of $5.00 milestone")
    print(f"  [{b}] {pct}%")
    if earnings.get("milestone_hit"):
        print("  Milestone hit! Your $5 bonus is pending.")
    else:
        remaining = max(0, (MILESTONE_MC - total_mc) / 100_000)
        print(f"  ${remaining:.4f} to go until your milestone.")
    print()

    # ── Your referral link ────────────────────────────────────────────────────
    install_cmd = (
        f"curl -fsSL https://raw.githubusercontent.com/bggprogramming/"
        f"claude-code-ads/main/install.sh | bash -s -- --ref {code}"
    )
    print(f"  Referral code: {code}")
    print(f"  Share this:")
    print(f"  {install_cmd}")
    print()
    print("  When someone you refer earns their first $5, you both get $5.")
    print()

    # ── People you referred ───────────────────────────────────────────────────
    referrals = fetch(cfg, f"users?referred_by=eq.{code}&select=referral_code,milestone_hit,created_at")
    if not referrals:
        print("  No referrals yet — share your link above.")
        return

    bonuses = fetch(cfg, f"referral_bonuses?referrer_code=eq.{code}&select=referred_code,status,triggered_at")
    bonus_map = {b["referred_code"]: b["status"] for b in bonuses}

    print(f"  ── Your referrals ({len(referrals)}) ────────────────────────")
    print(f"  {'Code':<10}  {'Status':<28}  {'Bonus'}")
    print(f"  {'────':<10}  {'──────':<28}  {'─────'}")

    pending_dollars = 0.0
    paid_dollars    = 0.0

    for r in referrals:
        rcode   = r["referral_code"]
        hit     = r.get("milestone_hit", False)
        bstatus = bonus_map.get(rcode, "")

        if hit:
            status_str = "Milestone hit ✓"
        else:
            status_str = "In progress..."

        if bstatus == "paid":
            bonus_str      = f"Paid ${BONUS_DOLLARS:.2f}"
            paid_dollars   += BONUS_DOLLARS
        elif bstatus == "pending":
            bonus_str      = f"Pending ${BONUS_DOLLARS:.2f}"
            pending_dollars += BONUS_DOLLARS
        else:
            bonus_str = "—"

        print(f"  {rcode:<10}  {status_str:<28}  {bonus_str}")

    print()
    if pending_dollars > 0:
        print(f"  Pending bonuses: ${pending_dollars:.2f}")
    if paid_dollars > 0:
        print(f"  Paid bonuses:    ${paid_dollars:.2f}")
    total_bonus = pending_dollars + paid_dollars
    if total_bonus > 0:
        print(f"  Total bonus:     ${total_bonus:.2f}")


if __name__ == "__main__":
    main()
