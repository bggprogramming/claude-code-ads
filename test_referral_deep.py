#!/usr/bin/env python3
"""
DEEP end-to-end verification of the referral mechanics against the LIVE backend.

Goes well beyond test_referral.py (single happy path). Exercises:
  A. Registration & attribution        (account fn, normalization, idempotency, RLS)
  B. Server-authoritative earnings      (no client forge; correct math)
  C. Milestone detection                (fires once, idempotent, threshold)
  D. Bonus creation                     (both parties, $10, dedup, no-referrer)
  E. Anti-fraud                         (daily cap, burst rate-limit, click-needs-impression)
  F. Dashboard surfacing                (referrer sees it; referred party — bug check)
  G. Multi-device                       (email identity vs. code-link milestone gap)

Test rows: ad_ids are prefixed `adv_test_` / events carry that ad_id, so the
track-event `cleanup_test` action (service role) removes them at the end. User
and referral_bonus rows created by milestone crossings cannot be deleted by anon
and are left behind (clearly tagged with the run id) — same caveat as the
existing harness.

Run: python3 test_referral_deep.py
"""
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import certifi

BASE    = Path(__file__).parent
CFG     = json.load(open(BASE / "config.json"))
URL     = CFG["supabase_url"]
KEY     = CFG["supabase_key"]
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

# Mirror of server constants (track-event/index.ts) for expectation math.
MILESTONE_MC     = 500_000
REFERRAL_BONUS_MC = 1_000_000
DEV_SHARE        = 0.9
CLICK_MULT       = 50
DAILY_CAP_MC     = 1_000_000
RATE_MAX         = 8

RUN = uuid.uuid4().hex[:6]                     # tag every row from this run
created_ad_ids = set()

results = []   # (severity, label, passed, detail)


# ── tiny HTTP helpers ─────────────────────────────────────────────────────────
def rest(method, path, payload=None, prefer="return=representation"):
    url = f"{URL}/rest/v1/{path}"
    headers = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    if payload is not None:
        headers["Prefer"] = prefer
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=12, context=SSL_CTX)
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read())
        except Exception: return e.code, None


def fn(name, payload, method="POST"):
    url = f"{URL}/functions/v1/{name}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=15, context=SSL_CTX)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:    return e.code, json.loads(e.read())
        except Exception: return e.code, {"error": f"http {e.code}"}


def track(uid, ad_id, event="impression", surface="completion", text="t"):
    return fn("track-event", {"ad_id": ad_id, "ad_text": text, "event": event,
                              "surface": surface, "user_id": uid})


def make_test_ad(bid_per_block_cents):
    """A paused/unpaid high-bid test advertiser. ad_id carries the cleanable prefix."""
    ad_id = f"adv_test_{RUN}_{len(created_ad_ids)}"
    created_ad_ids.add(ad_id)
    rest("POST", "advertisers", {
        "ad_id": ad_id, "company": "DeepTest", "email": "deeptest@example.com",
        "ad_text": "deep test", "url": "https://example.com",
        "cpm_cents": 2500, "bid_per_block_cents": bid_per_block_cents,
        "blocks": 100, "paid": False, "status": "paused",
    }, prefer="return=minimal")
    return ad_id


def account(email, referred_by=None):
    body = {"email": email}
    if referred_by:
        body["referred_by"] = referred_by
    return fn("account", body)


def check(label, passed, detail="", severity="normal"):
    results.append((severity, label, passed, detail))
    mark = "PASS" if passed else ("XFAIL" if severity == "bug" else "FAIL")
    print(f"   [{mark:5}] {label}" + (f"  →  {detail}" if detail else ""))
    return passed


def section(title):
    print(f"\n  ── {title} " + "─" * max(0, 58 - len(title)))


def bonuses_for(referrer_code):
    _, rows = rest("GET", f"referral_bonuses?referrer_code=eq.{referrer_code}"
                          "&select=referred_code,recipient,amount_millicents,status")
    return rows or []


def user_row(code):
    _, rows = rest("GET", f"users?referral_code=eq.{code}"
                          "&select=id,referral_code,referred_by,milestone_hit")
    return rows[0] if rows else None


def lifetime_mc(uid):
    _, rows = rest("GET", f"events?user_id=eq.{uid}&select=earnings_millicents")
    return sum(r.get("earnings_millicents", 0) for r in (rows or []))


# ══════════════════════════════════════════════════════════════════════════════
def main():
    print(f"\n  DEEP referral verification  (run={RUN})")
    print("  live backend:", URL)

    # ── A real referrer account that referred users point at ──────────────────
    st, ref = account(f"ref+{RUN}@deeptest.dev")
    referrer_code = ref.get("referral_code")
    if not referrer_code:
        print("  FATAL: could not create referrer account:", ref); sys.exit(1)
    print(f"  referrer account = {referrer_code}\n")

    # ── A. Registration & attribution ─────────────────────────────────────────
    section("A. Registration & attribution")

    st, a = account(f"refd+{RUN}@deeptest.dev", referred_by=referrer_code)
    referred_uid  = a.get("user_id")
    referred_code = a.get("referral_code")
    check("account() creates new referred account", bool(referred_uid) and a.get("existing") is False, str(a))
    row = user_row(referred_code)
    check("referred_by persisted on the new account",
          bool(row) and row.get("referred_by") == referrer_code,
          f"stored={row.get('referred_by') if row else None}")

    st, a2 = account(f"refd+{RUN}@deeptest.dev", referred_by="someoneelse")
    check("account() is idempotent for same email (same user_id, existing=true)",
          a2.get("user_id") == referred_uid and a2.get("existing") is True, str(a2))
    row = user_row(referred_code)
    check("referred_by NOT overwritten on repeat sign-in",
          bool(row) and row.get("referred_by") == referrer_code,
          f"stored={row.get('referred_by') if row else None}")

    st, a3 = account(f"norm+{RUN}@deeptest.dev", referred_by=f"  {referrer_code.upper()} !! ")
    norm_row = user_row(a3.get("referral_code", "")) if a3.get("referral_code") else None
    check("referred_by normalized (lowercase + strip non-alnum)",
          bool(norm_row) and norm_row.get("referred_by") == referrer_code,
          f"input='  {referrer_code.upper()} !! ' → stored={norm_row.get('referred_by') if norm_row else None}")

    st, bad = account("not-an-email")
    check("account() rejects invalid email", st == 400, f"http {st} {bad}")

    # anon direct INSERT (setup.py offline fallback) — and the RLS milestone guard
    direct_code = f"zd{RUN}"[:12]
    st, _ = rest("POST", "users",
                 {"id": str(uuid.uuid4()), "referral_code": direct_code,
                  "referred_by": referrer_code, "milestone_hit": False}, prefer="return=minimal")
    check("anon direct users INSERT works (offline fallback path)", st in (200, 201), f"http {st}")
    st, _ = rest("POST", "users",
                 {"id": str(uuid.uuid4()), "referral_code": f"zx{RUN}"[:12],
                  "referred_by": referrer_code, "milestone_hit": True}, prefer="return=minimal")
    check("anon CANNOT self-set milestone_hit=true (RLS blocks earning-escalation)",
          st not in (200, 201), f"http {st} (expected 4xx)")

    # ── B. Server-authoritative earnings ──────────────────────────────────────
    section("B. Server-authoritative earnings")

    ad_180 = make_test_ad(200_000)          # impMc = round(200000*0.9) = 180000
    fresh = str(uuid.uuid4())
    st, e = track(fresh, ad_180)
    expected_imp = round(200_000 * DEV_SHARE)
    check("impression earns server-computed 90% of bid (client cannot forge)",
          e.get("earnings_millicents") == expected_imp,
          f"got {e.get('earnings_millicents')} mc, expected {expected_imp}")

    # ── C + D. Milestone + bonus for a REFERRED user ──────────────────────────
    section("C. Milestone detection  +  D. Bonus creation")

    # referred_uid earns past $5 (3 × 180000 = 540000 > 500000)
    last = {}
    milestone_event_count = 0
    for _ in range(3):
        st, last = track(referred_uid, ad_180)
        if last.get("milestone_hit"):
            milestone_event_count += 1
    check("milestone_hit reported exactly once on crossing", milestone_event_count == 1,
          f"fired on {milestone_event_count} event(s); lifetime={last.get('total_millicents')}")
    time.sleep(0.5)
    row = user_row(referred_code)
    check("users.milestone_hit set true server-side", bool(row) and row.get("milestone_hit") is True, str(row))

    b = bonuses_for(referrer_code)
    mine = [x for x in b if x["referred_code"] == referred_code]
    check("two bonus rows created (referrer + referred)",
          {x["recipient"] for x in mine} == {"referrer", "referred"},
          str(sorted(x["recipient"] for x in mine)))
    check("each bonus = $10.00 (1,000,000 mc)",
          bool(mine) and all(x["amount_millicents"] == REFERRAL_BONUS_MC for x in mine),
          str([x["amount_millicents"] for x in mine]))

    # idempotency: earn one more — must NOT re-fire or duplicate bonuses
    st, again = track(referred_uid, ad_180)
    check("milestone does NOT re-fire after already hit", again.get("milestone_hit") is False,
          f"milestone_hit={again.get('milestone_hit')}")
    b2 = bonuses_for(referrer_code)
    mine2 = [x for x in b2 if x["referred_code"] == referred_code]
    check("no duplicate bonus rows after re-crossing", len(mine2) == 2, f"{len(mine2)} rows")

    # no-referrer user: crosses $5 but should mint NO bonus
    st, solo = account(f"solo+{RUN}@deeptest.dev")          # no referred_by
    solo_uid, solo_code = solo.get("user_id"), solo.get("referral_code")
    for _ in range(3):
        track(solo_uid, ad_180)
    time.sleep(0.3)
    _, solo_bon = rest("GET", f"referral_bonuses?referred_code=eq.{solo_code}&select=id")
    check("non-referred user hitting $5 mints NO bonus", not solo_bon, f"{len(solo_bon or [])} rows")

    # ── E. Anti-fraud ─────────────────────────────────────────────────────────
    section("E. Anti-fraud")

    # daily cap: one impression worth more than the $10/day cap is clamped
    ad_huge = make_test_ad(2_000_000)       # impMc = 1,800,000 > DAILY_CAP 1,000,000
    cap_uid = str(uuid.uuid4())
    st, c1 = track(cap_uid, ad_huge)
    check("daily earnings cap clamps a single oversized impression",
          c1.get("earnings_millicents") == DAILY_CAP_MC,
          f"got {c1.get('earnings_millicents')}, cap {DAILY_CAP_MC}")
    st, c2 = track(cap_uid, ad_huge)
    check("further earnings that day are clamped to 0 once capped",
          c2.get("earnings_millicents") == 0, f"got {c2.get('earnings_millicents')}")

    # burst rate-limit: >RATE_MAX events in the 10s window earn 0 + flag
    ad_small = make_test_ad(1_000)          # impMc = 900
    burst_uid = str(uuid.uuid4())
    flagged = False
    last_burst = {}
    for i in range(RATE_MAX + 3):
        st, last_burst = track(burst_uid, ad_small)
        if last_burst.get("rate_limited"):
            flagged = True
    check("burst rate-limit trips after RATE_MAX events in the window",
          flagged and last_burst.get("earnings_millicents") == 0,
          f"rate_limited={last_burst.get('rate_limited')} last_mc={last_burst.get('earnings_millicents')}")

    # click only earns 50x when a matching recent impression exists
    ad_click = make_test_ad(1_000)          # impMc = 900
    click_uid = str(uuid.uuid4())
    st, bare_click = track(click_uid, ad_click, event="click", surface="click")
    check("click with NO prior impression is priced as an impression (not 50x)",
          bare_click.get("earnings_millicents") == 900,
          f"got {bare_click.get('earnings_millicents')}, expected 900")
    track(click_uid, ad_click, event="impression", surface="completion")
    st, good_click = track(click_uid, ad_click, event="click", surface="click")
    check("click WITH a recent impression earns the 50x multiplier",
          good_click.get("earnings_millicents") == 900 * CLICK_MULT,
          f"got {good_click.get('earnings_millicents')}, expected {900*CLICK_MULT}")

    # ── F. Dashboard surfacing ────────────────────────────────────────────────
    section("F. Dashboard surfacing of the bonus")

    # Referrer's view (referral.py / dev-portal query by their own code)
    ref_view = bonuses_for(referrer_code)
    referrer_sees = any(x["referred_code"] == referred_code and x["recipient"] == "referrer"
                        for x in ref_view)
    check("referrer's dashboard query surfaces their $10 bonus", referrer_sees,
          f"{len(ref_view)} rows visible to referrer")

    # Referred party's view: load their portal via the deployed dev-portal fn and
    # confirm the signup bonus is now surfaced (the fix queries referral_bonuses
    # by referred_code too, instead of only referrer_code).
    st, portal = fn(f"dev-portal?code={referred_code}", None, method="GET")
    referred_sees = bool(portal.get("has_signup_bonus")) and \
        (portal.get("signup_bonus_pending_dollars", 0) + portal.get("signup_bonus_paid_dollars", 0)) >= 10.0
    check("referred party's portal surfaces their own $10 signup bonus", referred_sees,
          f"has_signup_bonus={portal.get('has_signup_bonus')} "
          f"pending=${portal.get('signup_bonus_pending_dollars')} paid=${portal.get('signup_bonus_paid_dollars')}")

    # ── G. Multi-device ───────────────────────────────────────────────────────
    section("G. Multi-device earnings vs. milestone")

    # G1 — email identity: same email twice → SAME user_id (events aggregate, so
    # milestone math is correct for the common multi-machine case).
    st, m1 = account(f"multi+{RUN}@deeptest.dev")
    st, m2 = account(f"multi+{RUN}@deeptest.dev")
    check("same email on two machines returns ONE shared account (earnings aggregate)",
          m1.get("user_id") == m2.get("user_id"), f"{m1.get('user_id')} vs {m2.get('user_id')}")

    # G2 — code-link path: two DISTINCT device accounts, each earning <$5, linked.
    # Portal aggregates to >$5, but track-event evaluates milestone per single
    # user_id, so neither device crosses → no milestone, no bonus, despite the
    # household clearly having earned the referral threshold.
    st, d1 = account(f"dev1+{RUN}@deeptest.dev", referred_by=referrer_code)
    st, d2 = account(f"dev2+{RUN}@deeptest.dev")
    d1_uid, d1_code = d1["user_id"], d1["referral_code"]
    d2_uid, d2_code = d2["user_id"], d2["referral_code"]
    ad_link = make_test_ad(100_000)          # impMc = 90000
    for _ in range(3):                       # 3*90000 = 270000 (<500000) on each device
        track(d1_uid, ad_link)
        track(d2_uid, ad_link)
    # Before linking, neither device individually crossed $5.
    r1b, r2b = user_row(d1_code), user_row(d2_code)
    check("pre-link: neither split device crossed $5 on its own",
          not (r1b and r1b.get("milestone_hit")) and not (r2b and r2b.get("milestone_hit")),
          f"d1={r1b.get('milestone_hit') if r1b else None} d2={r2b.get('milestone_hit') if r2b else None}")
    # Link d2 into d1, then fire one more event — the milestone now evaluates over
    # the whole household (270k + 270k + 90k = 630k > 500k) and pays out.
    st, link_res = fn("link-device", {"code": d1_code, "device_code": d2_code})
    st, trig = track(d1_uid, ad_link)
    household_mc = lifetime_mc(d1_uid) + lifetime_mc(d2_uid)
    r1 = user_row(d1_code)                    # d1 is the primary
    _, link_bonus = rest("GET", f"referral_bonuses?referred_code=eq.{d1_code}&recipient=eq.referrer&select=id")
    check("linked household earned >$5 across devices",
          household_mc >= MILESTONE_MC, f"household={household_mc} mc (link ok={link_res.get('ok')})")
    check("split-device household triggers milestone+bonus after linking",
          bool(r1 and r1.get("milestone_hit")) and bool(link_bonus),
          f"primary milestone_hit={r1.get('milestone_hit') if r1 else None}, "
          f"bonus rows={len(link_bonus or [])}, trig_milestone={trig.get('milestone_hit')}")

    # ── cleanup ───────────────────────────────────────────────────────────────
    section("Cleanup (service-role cleanup_test on test-prefixed ad_ids)")
    for ad_id in sorted(created_ad_ids):
        st, r = fn("track-event", {"action": "cleanup_test", "ad_id": ad_id})
        print(f"   cleaned {ad_id}: events={r.get('events_deleted')} advertisers={r.get('advertisers_deleted')}")

    # ── summary ───────────────────────────────────────────────────────────────
    print("\n  " + "═" * 60)
    real_fail = [r for r in results if not r[2] and r[0] != "bug"]
    bugs      = [r for r in results if not r[2] and r[0] == "bug"]
    passed    = [r for r in results if r[2]]
    print(f"  {len(passed)} passed   {len(real_fail)} unexpected failures   {len(bugs)} confirmed bug(s)")
    if real_fail:
        print("\n  UNEXPECTED FAILURES (regressions):")
        for _, label, _, detail in real_fail:
            print(f"    ✗ {label} — {detail}")
    if bugs:
        print("\n  CONFIRMED BUGS (expected-fail demonstrations):")
        for _, label, _, detail in bugs:
            print(f"    ⚠ {label}\n        {detail}")
    print(f"\n  (test users/bonuses tagged '{RUN}' remain — anon cannot DELETE them.)\n")


if __name__ == "__main__":
    main()
