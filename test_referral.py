#!/usr/bin/env python3
"""
End-to-end referral flow test (server-authoritative).

Simulates:
  1. A new developer installs via your referral link (referred_by = your code)
  2. They accumulate impressions via the track-event edge function and cross $5
  3. track-event (server-side) marks the milestone and inserts the $10/$10 bonus
  4. referral.py shows the referral

Earnings and bonuses are computed/created server-side now — clients can no longer
write events or referral_bonuses directly (RLS), so this drives the real edge
function path rather than calling earnings._push_milestone with the anon key.

Note: the anon role cannot DELETE, so test rows are left in Supabase and cleaned
out of band (service role). Each run uses a fresh random code to avoid collisions.

Run: python3 ~/.claude/ads/test_referral.py
"""
import json
import random
import ssl
import string
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import certifi

BASE     = Path(__file__).parent
CFG_FILE = BASE / "config.json"
SSL_CTX  = ssl.create_default_context(cafile=certifi.where())
SEP      = "  " + "─" * 50


def load_config():
    with open(CFG_FILE) as f:
        return json.load(f)


def api(cfg, method, path, payload=None, params="", prefer="return=minimal"):
    url = f"{cfg['supabase_url']}/rest/v1/{path}{params}"
    headers = {
        "apikey":        cfg["supabase_key"],
        "Authorization": f"Bearer {cfg['supabase_key']}",
        "Content-Type":  "application/json",
    }
    if payload is not None:
        headers["Prefer"] = prefer
    data = json.dumps(payload).encode() if payload else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=10, context=SSL_CTX)
    body = resp.read()
    return json.loads(body) if body else None


def track_event(cfg, payload):
    """Record an event via the track-event edge function (server computes earnings)."""
    url = f"{cfg['supabase_url']}/functions/v1/track-event"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=10, context=SSL_CTX).read())


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  →  {detail}" if detail else ""))
    return condition


def rand(n):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def main():
    cfg = load_config()
    referrer_code = cfg.get("referral_code")
    if not referrer_code:
        print("  ERROR: No referral_code in config. Run setup.py first.")
        sys.exit(1)

    test_uid  = str(uuid.uuid4())
    test_code = "t" + rand(5)             # unique per run
    test_adid = "adv_reftest_" + rand(6)  # temp high-CPM ad to cross $5 quickly

    print()
    print("  End-to-end referral flow test (server-authoritative)")
    print(SEP)

    # ── Step 1: Register the referred user ────────────────────────────────────
    print()
    print("  Step 1 — New developer installs via referral link")
    print(f"  (referred_by = {referrer_code})")
    print()

    reg_ok = True
    try:
        api(cfg, "POST", "users", {
            "id": test_uid, "referral_code": test_code,
            "referred_by": referrer_code, "milestone_hit": False,
        })
    except Exception as e:
        reg_ok = False
        print(f"  Registration error: {e}")
    check("Test user registered (anon INSERT users)", reg_ok,
          f"code={test_code} referred_by={referrer_code}")

    rows = api(cfg, "GET",
               f"users?referral_code=eq.{test_code}&select=referred_by,milestone_hit")
    check("referred_by stored correctly",
          bool(rows) and rows[0].get("referred_by") == referrer_code,
          str(rows[0] if rows else "no rows"))

    print()
    print(SEP)

    # ── Step 2: Earn impressions via track-event until the $5 milestone ───────
    print()
    print("  Step 2 — Earn impressions through track-event until $5 milestone")
    print()

    # Temp advertiser with a high bid so a handful of impressions crosses $5.
    # Developer earns 90% of the bid per impression: bid_per_block_cents 200000
    # → 180,000 mc/impression; 3 impressions → 540,000 (> 500,000 milestone).
    try:
        api(cfg, "POST", "advertisers", {
            "ad_id": test_adid, "company": "RefTest", "email": "reftest@example.com",
            "ad_text": "ref test", "url": "https://example.com",
            "cpm_cents": 200000, "bid_per_block_cents": 200000, "blocks": 10,
            "paid": False, "status": "paused",   # test row — not in the live auction
        })
    except Exception as e:
        print(f"  (temp advertiser insert error: {e})")

    milestone_seen = False
    last = {}
    for _ in range(6):
        last = track_event(cfg, {
            "ad_id": test_adid, "ad_text": "ref test",
            "event": "impression", "surface": "completion", "user_id": test_uid,
        })
        if last.get("milestone_hit"):
            milestone_seen = True

    check("track-event computes earnings server-side",
          last.get("earnings_millicents") == 100000,
          f"{last.get('earnings_millicents')} mc/impression (expected 100000)")
    check("track-event reports milestone crossed", milestone_seen,
          f"cumulative={last.get('total_millicents')} mc")

    time.sleep(1)

    print()
    print(SEP)

    # ── Step 3: Verify server-side milestone + bonus ──────────────────────────
    print()
    print("  Step 3 — Verify Supabase recorded the milestone + $10/$10 bonus")
    print()

    user_rows = api(cfg, "GET", f"users?referral_code=eq.{test_code}&select=milestone_hit")
    milestone_set = bool(user_rows) and user_rows[0].get("milestone_hit") is True
    check("users.milestone_hit = true (set server-side)", milestone_set,
          str(user_rows[0] if user_rows else "no rows"))

    bonus_rows = api(cfg, "GET",
        f"referral_bonuses?referrer_code=eq.{referrer_code}&referred_code=eq.{test_code}"
        f"&select=amount_millicents,status,recipient")
    bonus_exists = bool(bonus_rows)
    correct_amt  = bonus_exists and all(b.get("amount_millicents") == 1_000_000 for b in bonus_rows)
    both_parties = bonus_exists and {b.get("recipient") for b in bonus_rows} == {"referrer", "referred"}

    check("referral_bonuses rows created", bonus_exists,
          f"{len(bonus_rows) if bonus_rows else 0} rows")
    check("Amount = $10.00 (1,000,000 mc) each", correct_amt,
          str(bonus_rows[0]["amount_millicents"]) if bonus_exists else "—")
    check("Bonus created for BOTH referrer + referred", both_parties,
          str(sorted(b.get("recipient") for b in bonus_rows)) if bonus_exists else "—")

    print()
    print(SEP)

    # ── Step 4: referral.py dashboard ─────────────────────────────────────────
    print()
    print("  Step 4 — referral.py dashboard (your view as the referrer)")
    print()

    import subprocess
    result = subprocess.run(
        ["python3", str(BASE / "referral.py")],
        capture_output=True, text=True,
    )
    check("referral.py shows the test referral", test_code in result.stdout)

    print()
    print("  (anon cannot DELETE — test rows remain in Supabase, cleaned out of band.)")
    print()
    print(SEP)

    # ── Summary ───────────────────────────────────────────────────────────────
    all_pass = (milestone_seen and milestone_set and bonus_exists
                and correct_amt and both_parties)
    print()
    if all_pass:
        print("  All checks passed. Server-side referral flow is working end to end.")
    else:
        print("  Some checks failed — see above.")
    print()


if __name__ == "__main__":
    main()
