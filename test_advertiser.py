#!/usr/bin/env python3
"""
End-to-end test for the self-serve advertiser checkout + analytics dashboard.

Tests:
  1. Create a campaign via the Supabase REST API (mirrors advertise.html form submit)
  2. Verify campaign is in the advertisers table with correct fields
  3. Retrieve campaign via dashboard_key (what dashboard.html does on load)
  4. Insert test impression + click events for the campaign
  5. Query events by ad_id (verifies anon SELECT policy on events is live)
  6. Verify aggregated analytics match expectations
  7. Verify seeded advertisers (Cursor, Warp, Linear) have real impression data
  8. Clean up test rows

Run: python3 ~/.claude/ads/test_advertiser.py
"""
import json
import random
import ssl
import string
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import certifi

BASE     = Path(__file__).parent
CFG_FILE = BASE / "config.json"
SSL_CTX  = ssl.create_default_context(cafile=certifi.where())
SEP      = "  " + "─" * 52


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
    """Record an event via the track-event edge function (anon INSERT on events
    is revoked; earnings are computed server-side)."""
    url = f"{cfg['supabase_url']}/functions/v1/track-event"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=10, context=SSL_CTX)
    return json.loads(resp.read())


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    suffix = f"  →  {detail}" if detail else ""
    print(f"  [{mark}] {label}{suffix}")
    return condition


def gen_ad_id():
    return "adv_test_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def main():
    cfg = load_config()
    results = []

    print()
    print("  Self-serve advertiser checkout + analytics dashboard — E2E test")
    print(SEP)

    # ── Step 1: Create campaign (mirrors advertise.html form submit) ──────────
    print()
    print("  Step 1 — Create campaign via self-serve checkout")
    print()

    test_ad_id = gen_ad_id()
    campaign_payload = {
        "ad_id":              test_ad_id,
        "company":            "TestCo",
        "email":              "test@testco.com",
        "ad_text":            "✦ TestCo — Ship twice as fast. testco.com",
        "url":                "https://testco.com",
        "cpm_cents":          2500,
        "bid_per_block_cents": 2500,
        "daily_budget_cents": 10000,
        "status":             "paused",   # test row — must NOT enter the live auction
        "paid":               False,
    }

    created = None
    try:
        rows = api(cfg, "POST", "advertisers", campaign_payload,
                   params="?select=ad_id,company,status,cpm_cents,dashboard_key",
                   prefer="return=representation")
        created = rows[0] if isinstance(rows, list) else rows
    except Exception as e:
        print(f"  ERROR creating campaign: {e}")

    results.append(check("Campaign row created in advertisers table",
                         created is not None, f"ad_id={test_ad_id}"))
    if created is None:
        print("  Cannot continue without a created campaign.")
        sys.exit(1)

    results.append(check("dashboard_key is a non-empty UUID",
                         bool(created.get("dashboard_key")) and len(created["dashboard_key"]) == 36,
                         created.get("dashboard_key", "MISSING")))

    results.append(check("status stored ('paused' test row — not in live auction)",
                         created.get("status") == "paused",
                         created.get("status")))

    results.append(check("cpm_cents stored correctly",
                         created.get("cpm_cents") == 2500,
                         str(created.get("cpm_cents"))))

    dashboard_key = created["dashboard_key"]
    print(f"  Dashboard URL: dashboard.html?key={dashboard_key}")

    print()
    print(SEP)

    # ── Step 2: Retrieve campaign via dashboard_key (mirrors dashboard.html) ──
    print()
    print("  Step 2 — Retrieve campaign by dashboard_key (as dashboard.html does)")
    print()

    fetched = None
    try:
        rows = api(cfg, "GET", "advertisers",
                   params=f"?dashboard_key=eq.{dashboard_key}"
                          f"&select=ad_id,company,ad_text,url,cpm_cents,status,dashboard_key")
        fetched = rows[0] if rows else None
    except Exception as e:
        print(f"  ERROR fetching by dashboard_key: {e}")

    results.append(check("Campaign retrieved by dashboard_key",
                         fetched is not None and fetched.get("ad_id") == test_ad_id,
                         f"ad_id={fetched.get('ad_id') if fetched else 'NOT FOUND'}"))

    results.append(check("company field matches",
                         fetched and fetched.get("company") == "TestCo",
                         fetched.get("company") if fetched else "—"))

    print()
    print(SEP)

    # ── Step 3: Insert test events for the campaign ───────────────────────────
    print()
    print("  Step 3 — Insert test impression + click events")
    print()

    # Earnings are computed server-side from the campaign's bid (auction model):
    # developer earns 90% of the bid per impression, flat across surfaces.
    # bid_per_block_cents 2500 → 2250 mc/impression; click = 0.
    test_events = [
        {"ad_id": test_ad_id, "ad_text": campaign_payload["ad_text"],
         "event": "impression", "surface": "statusline", "user_id": "test-user-1"},
        {"ad_id": test_ad_id, "ad_text": campaign_payload["ad_text"],
         "event": "impression", "surface": "spinner", "user_id": "test-user-1"},
        {"ad_id": test_ad_id, "ad_text": campaign_payload["ad_text"],
         "event": "impression", "surface": "statusline", "user_id": "test-user-2"},
        {"ad_id": test_ad_id, "ad_text": campaign_payload["ad_text"],
         "event": "click", "surface": "click", "user_id": "test-user-1"},
    ]

    inserted = 0
    for ev in test_events:
        try:
            res = track_event(cfg, ev)
            if res.get("ok"):
                inserted += 1
        except Exception as e:
            print(f"  ERROR inserting event: {e}")

    results.append(check(f"Inserted {len(test_events)} test events",
                         inserted == len(test_events),
                         f"{inserted}/{len(test_events)} succeeded"))

    print()
    print(SEP)

    # ── Step 4: Query events by ad_id (anon SELECT policy) ────────────────────
    print()
    print("  Step 4 — Query events by ad_id (verifies anon SELECT policy on events)")
    print()

    event_rows = None
    try:
        event_rows = api(cfg, "GET", "events",
                         params=f"?ad_id=eq.{test_ad_id}&select=event,surface,earnings_millicents")
    except Exception as e:
        print(f"  ERROR querying events: {e}")

    results.append(check("Events queryable by ad_id (anon SELECT works)",
                         event_rows is not None,
                         f"{len(event_rows)} rows" if event_rows else "FAILED"))

    if event_rows is not None:
        impressions = [e for e in event_rows if e["event"] == "impression"]
        clicks      = [e for e in event_rows if e["event"] == "click"]
        total_mc    = sum(e.get("earnings_millicents", 0) or 0 for e in impressions)

        results.append(check("Impression count matches",
                             len(impressions) == 3, f"{len(impressions)} impressions"))
        results.append(check("Click count matches",
                             len(clicks) == 1, f"{len(clicks)} clicks"))

        ctr = len(clicks) / len(impressions) * 100 if impressions else 0
        results.append(check("CTR computable",
                             abs(ctr - 33.33) < 0.1,
                             f"{ctr:.2f}% (expected 33.33%)"))

        spend = (campaign_payload["cpm_cents"] / 100) * len(impressions) / 1000
        results.append(check("Est. spend calculation",
                             abs(spend - 0.075) < 0.001,
                             f"${spend:.4f} (expected $0.0750)"))

        results.append(check("earnings_millicents stored correctly (3 × 2250 = dev 90% of bid)",
                             total_mc == 6750,
                             f"{total_mc} mc = ${total_mc/100000:.5f}"))

    print()
    print(SEP)

    # ── Step 5: Verify the built-in house ads are served by the ad-feed function ──
    print()
    print("  Step 5 — Verify built-in house ads (Cursor, Warp, Linear) are served")
    print()

    feed_ids = set()
    try:
        url = f"{cfg['supabase_url']}/functions/v1/ad-feed"
        req = urllib.request.Request(url, headers={"User-Agent": "test"})
        body = json.loads(urllib.request.urlopen(req, timeout=10, context=SSL_CTX).read())
        feed_ids = {a.get("id") for a in body.get("ads", [])}
    except Exception as e:
        print(f"  ad-feed fetch error: {e}")

    for ad_id, company in [("ad_cursor", "Cursor"), ("ad_warp", "Warp"), ("ad_linear", "Linear")]:
        results.append(check(
            f"{company}: served by ad-feed (house ad)",
            ad_id in feed_ids,
            "in feed ✓" if ad_id in feed_ids else "NOT in feed"
        ))

    print()
    print(SEP)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    print()
    print("  Cleaning up test rows…")
    try:
        api(cfg, "DELETE", "events", params=f"?ad_id=eq.{test_ad_id}")
        api(cfg, "DELETE", "advertisers", params=f"?ad_id=eq.{test_ad_id}")
        print("  Cleaned.")
    except Exception as e:
        print(f"  Cleanup error (manual cleanup may be needed): {e}")

    print()

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r)
    total  = len(results)
    print(SEP)
    print()
    if passed == total:
        print(f"  All {total} checks passed. Advertiser checkout + analytics flow is working end to end.")
    else:
        print(f"  {passed}/{total} checks passed — see FAIL lines above.")
    print()


if __name__ == "__main__":
    main()
