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

sys.path.insert(0, str(BASE))
from earnings import MILESTONE_MC, REFERRAL_BONUS_MC   # single source of truth
BONUS_DOLLARS = REFERRAL_BONUS_MC / 100_000            # $10 each way
SUPABASE_URL_BASE = "https://gpbrzpyvzlzwvvymgeyk.supabase.co"
BADGE_FN_BASE     = f"{SUPABASE_URL_BASE}/functions/v1/badge"
SHIELDS_BASE      = "https://img.shields.io/endpoint"
SITE_BASE         = "https://bggprogramming.github.io/mango"


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
        print("  Milestone hit! Your $10 referral bonus is pending.")
    else:
        remaining = max(0, (MILESTONE_MC - total_mc) / 100_000)
        print(f"  ${remaining:.4f} to go until your milestone.")
    print()

    # ── Your own signup bonus (if someone referred YOU) ───────────────────────
    # The bonus row crediting the referred party carries the *inviter's* code as
    # referrer_code, so it's found by referred_code (your code) + recipient.
    signup = fetch(cfg, f"referral_bonuses?referred_code=eq.{code}"
                        f"&recipient=eq.referred&select=status,amount_millicents")
    if signup:
        amt    = signup[0].get("amount_millicents", REFERRAL_BONUS_MC) / 100_000
        status = signup[0].get("status", "pending")
        if status == "paid":
            print(f"  Signup bonus: ${amt:.2f} paid — thanks for joining via a friend.")
        else:
            print(f"  Signup bonus: ${amt:.2f} pending (you joined via a referral).")
        print()

    # ── Your referral link ────────────────────────────────────────────────────
    install_cmd = (
        f"curl -fsSL https://raw.githubusercontent.com/bggprogramming/"
        f"mango/main/install.sh | bash -s -- --ref {code}"
    )
    invite_url   = f"{SITE_BASE}/invite.html?ref={code}"
    site_link    = f"{SITE_BASE}/?ref={code}"
    badge_url    = f"{BADGE_FN_BASE}/{code}"
    shields_url  = f"{SHIELDS_BASE}?url={badge_url}&style=flat"
    badge_md     = f"[![Earned with Mango]({shields_url})]({site_link})"

    earned_str = f"${earned:.2f}" if earned >= 0.01 else "money"
    invite_msg = (
        f"i'm getting paid to code — the ads in my terminal pay me 90% "
        f"(made {earned_str} so far). join with my link and we both get $10:\n{invite_url}"
    )

    print(f"  Referral code: {code}")
    print(f"  Your portal (bookmark — opens straight to your earnings):")
    print(f"  {SITE_BASE}/portal.html?code={code}")
    print()
    print("  ── Invite a friend (you both get $10) ───────────────────────────")
    print("  Send this on iMessage — the link shows a rich preview:")
    print()
    for line in invite_msg.split("\n"):
        print(f"    {line}")
    print()

    # Copy the invite message straight to the clipboard on macOS.
    try:
        import subprocess
        subprocess.run(["pbcopy"], input=invite_msg.encode(), check=True, timeout=3)
        print("  ✓ Copied to your clipboard — just paste it into Messages.")
        try:
            import funnel; funnel.log("referral_shared")
        except Exception:
            pass
    except Exception:
        print(f"  Direct install link: {invite_url}")
    print()
    print(f"  (raw install command: {install_cmd})")
    print()
    print("  ── GitHub README badge ─────────────────────────────────────────")
    print("  Add this to your README to show live earnings and drive referrals:")
    print()
    print(f"  {badge_md}")
    print()
    print(f"  Live badge: {shields_url}")
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
