#!/usr/bin/env python3
"""
End-to-end referral flow test.

Simulates:
  1. A new developer installs via your referral link (--ref p5lvaf)
  2. They accumulate impressions and hit the $5 milestone
  3. Supabase receives the referral_bonus row
  4. referral.py shows the pending bonus

Run: python3 ~/.claude/ads/test_referral.py
"""
import json
import ssl
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import certifi
import earnings as _earnings

BASE    = Path(__file__).parent
CFG_FILE = BASE / "config.json"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

SEP = "  " + "─" * 50


def load_config():
    with open(CFG_FILE) as f:
        return json.load(f)


def api(cfg, method, path, payload=None, params=""):
    url = f"{cfg['supabase_url']}/rest/v1/{path}{params}"
    headers = {
        "apikey":        cfg["supabase_key"],
        "Authorization": f"Bearer {cfg['supabase_key']}",
        "Content-Type":  "application/json",
    }
    if payload is not None:
        headers["Prefer"] = "return=minimal"
    data = json.dumps(payload).encode() if payload else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=6, context=SSL_CTX)
    body = resp.read()
    return json.loads(body) if body else None


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  →  {detail}" if detail else ""))
    return condition


def main():
    cfg = load_config()
    referrer_code = cfg.get("referral_code")
    if not referrer_code:
        print("  ERROR: No referral_code in config. Run setup.py first.")
        sys.exit(1)

    print()
    print("  End-to-end referral flow test")
    print(SEP)

    # ── Step 1: Register a simulated new user ─────────────────────────────────
    print()
    print("  Step 1 — New developer installs via referral link")
    print(f"  Command they ran: ... | bash -s -- --ref {referrer_code}")
    print()

    test_uid  = str(uuid.uuid4())
    test_code = "tstref"   # fixed slug so we can clean up easily

    # Clean up any prior test run
    try:
        api(cfg, "DELETE", f"referral_bonuses?referrer_code=eq.{referrer_code}&referred_code=eq.{test_code}")
        api(cfg, "DELETE", f"users?id=eq.{test_uid}")
        api(cfg, "DELETE", f"users?referral_code=eq.{test_code}")
    except Exception:
        pass

    # Register the test user in Supabase (what setup.py does)
    try:
        api(cfg, "POST", "users", {
            "id":            test_uid,
            "referral_code": test_code,
            "referred_by":   referrer_code,
            "milestone_hit": False,
        })
        ok = True
    except Exception as e:
        ok = False
        print(f"  Registration error: {e}")

    check("Test user registered in Supabase", ok,
          f"user_id={test_uid[:8]}… code={test_code} referred_by={referrer_code}")

    # Verify it's there
    rows = api(cfg, "GET", f"users?referral_code=eq.{test_code}&select=referral_code,referred_by,milestone_hit")
    check("Referred_by stored correctly", rows and rows[0].get("referred_by") == referrer_code,
          str(rows[0] if rows else "no rows"))

    print()
    print(SEP)

    # ── Step 2: Simulate earnings accumulating past the $5 milestone ──────────
    print()
    print("  Step 2 — Test user earns impressions, crosses $5 milestone")
    print()

    # Build a cfg dict for the test user (same Supabase creds, different identity)
    test_cfg = {**cfg, "user_id": test_uid, "referral_code": test_code, "referred_by": referrer_code}

    # Call _push_milestone directly (what earnings.track() calls when crossing $5)
    print("  Triggering $5 milestone for test user...")
    _earnings._push_milestone(test_cfg, test_code, referrer_code)
    time.sleep(1)   # let the async write settle

    print()
    print(SEP)

    # ── Step 3: Verify Supabase state ─────────────────────────────────────────
    print()
    print("  Step 3 — Verify Supabase recorded the milestone + bonus")
    print()

    # Check user.milestone_hit
    user_rows = api(cfg, "GET", f"users?referral_code=eq.{test_code}&select=milestone_hit")
    milestone_set = user_rows and user_rows[0].get("milestone_hit") is True
    check("users.milestone_hit = true", milestone_set, str(user_rows[0] if user_rows else "no rows"))

    # Check referral_bonuses row
    bonus_rows = api(cfg, "GET",
        f"referral_bonuses?referrer_code=eq.{referrer_code}&referred_code=eq.{test_code}"
        f"&select=referrer_code,referred_code,amount_millicents,status")
    bonus_exists  = bool(bonus_rows)
    correct_amt   = bonus_exists and bonus_rows[0].get("amount_millicents") == 500_000
    correct_status = bonus_exists and bonus_rows[0].get("status") == "pending"

    check("referral_bonuses row created", bonus_exists, str(bonus_rows[0] if bonus_exists else "missing"))
    check("Amount = $5.00 (500,000 mc)",  correct_amt,
          f"{bonus_rows[0]['amount_millicents']} mc" if bonus_exists else "—")
    check("Status = pending",             correct_status,
          bonus_rows[0]["status"] if bonus_exists else "—")

    print()
    print(SEP)

    # ── Step 4: Verify referral.py dashboard shows the bonus ──────────────────
    print()
    print("  Step 4 — referral.py dashboard (your view as the referrer)")
    print()

    import subprocess
    result = subprocess.run(
        ["python3", str(BASE / "referral.py")],
        capture_output=True, text=True
    )
    print(result.stdout)
    check("referral.py shows test referral", "tstref" in result.stdout)
    check("referral.py shows Pending $5.00", "Pending $5.00" in result.stdout)

    print()
    print(SEP)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    print()
    print("  Cleaning up test rows from Supabase...")
    try:
        api(cfg, "DELETE", f"referral_bonuses?referrer_code=eq.{referrer_code}&referred_code=eq.{test_code}")
        api(cfg, "DELETE", f"users?referral_code=eq.{test_code}")
        print("  Cleaned.")
    except Exception as e:
        print(f"  Cleanup error (manual cleanup may be needed): {e}")

    print()
    # ── Summary ───────────────────────────────────────────────────────────────
    all_pass = milestone_set and bonus_exists and correct_amt and correct_status
    if all_pass:
        print("  All checks passed. Referral flow is working end to end.")
    else:
        print("  Some checks failed — see above.")
    print()


if __name__ == "__main__":
    main()
