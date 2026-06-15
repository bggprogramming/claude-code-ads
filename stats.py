#!/usr/bin/env python3
"""
Ad analytics dashboard — run directly or ask Claude to run it.
Shows impressions by surface (spinner / statusline), clicks, CTR per ad,
earnings summary, and CTR benchmark vs web display.
"""
import json
import sqlite3
from pathlib import Path

DB_FILE = Path(__file__).parent / "analytics.db"

# Industry CTR benchmarks for comparison
WEB_DISPLAY_CTR   = 0.15   # Google Display Network avg
SEARCH_ADS_CTR    = 3.17   # avg search ad CTR
IN_TERMINAL_BENCH = 2.1    # our documented avg

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
DIM    = "\033[2m"
CYAN   = "\033[36m"


def ctr_color(pct):
    if pct >= 1.5:
        return GREEN
    if pct >= 0.5:
        return YELLOW
    return ""


def bar(frac, width=20):
    filled = min(int(frac * width), width)
    return "█" * filled + "░" * (width - filled)


def main():
    if not DB_FILE.exists():
        print("No analytics data yet. Run ad.py first.")
        return

    conn = sqlite3.connect(DB_FILE)

    print()
    print(f"{BOLD}╔══════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║           Ad Analytics Dashboard                 ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════╝{RESET}")

    # ── Per-ad totals ──────────────────────────────────────────────────────────
    rows = conn.execute("""
        SELECT
            ad_id,
            ad_text,
            COUNT(*) FILTER (WHERE event = 'impression')              AS impressions,
            COUNT(*) FILTER (WHERE event = 'impression'
                             AND surface = 'spinner')                  AS spinner,
            COUNT(*) FILTER (WHERE event = 'impression'
                             AND surface = 'statusline')               AS statusline,
            COUNT(*) FILTER (WHERE event = 'click')                   AS clicks,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE event = 'click') /
                MAX(1, COUNT(*) FILTER (WHERE event = 'impression')), 2
            ) AS ctr_pct
        FROM events
        WHERE ad_text != ''
        GROUP BY ad_id, ad_text
        ORDER BY impressions DESC
    """).fetchall()

    if not rows:
        print("\n  No events recorded yet.")
        conn.close()
        return

    max_imp = max(r[2] for r in rows) or 1
    print()
    for ad_id, ad_text, impressions, spinner, statusline, clicks, ctr in rows:
        b        = bar(impressions / max_imp)
        cc       = ctr_color(ctr)
        web_mult = round(ctr / WEB_DISPLAY_CTR, 1) if ctr > 0 else 0
        print(f"  {DIM}{ad_id}{RESET}")
        print(f"  {ad_text[:70]}")
        print(f"  [{b}] {BOLD}{impressions}{RESET} impressions  "
              f"{DIM}({spinner} spinner / {statusline} statusline){RESET}")
        print(f"  {clicks} clicks  ·  {cc}{BOLD}{ctr:.2f}%{RESET} CTR", end="")
        if ctr > 0:
            print(f"  {DIM}← {web_mult}× web display ({WEB_DISPLAY_CTR}% avg){RESET}", end="")
        print()
        print()

    # ── Surface totals ─────────────────────────────────────────────────────────
    surfaces = conn.execute("""
        SELECT surface, COUNT(*) AS n
        FROM events
        GROUP BY surface
        ORDER BY n DESC
    """).fetchall()

    print(f"  {DIM}── By surface ──────────────────────────────{RESET}")
    for surface, n in surfaces:
        print(f"  {(surface or 'unknown'):14}  {n}")

    # ── Grand totals ───────────────────────────────────────────────────────────
    totals = conn.execute("""
        SELECT
            COUNT(*) FILTER (WHERE event = 'impression') AS total_imp,
            COUNT(*) FILTER (WHERE event = 'click')      AS total_clicks
        FROM events
    """).fetchone()
    total_imp    = totals[0] or 0
    total_clicks = totals[1] or 0
    overall_ctr  = total_clicks / total_imp * 100 if total_imp else 0

    print()
    print(f"  {BOLD}Total:{RESET} {total_imp} impressions · "
          f"{total_clicks} clicks · "
          f"{ctr_color(overall_ctr)}{BOLD}{overall_ctr:.2f}%{RESET} overall CTR")

    # ── CTR benchmark ──────────────────────────────────────────────────────────
    print()
    print(f"  {DIM}── CTR benchmarks ──────────────────────────{RESET}")
    bmarks = [
        ("This network",         overall_ctr,       GREEN if overall_ctr >= 1.5 else ""),
        ("In-terminal (est)",    IN_TERMINAL_BENCH,  CYAN),
        ("Search ads avg",       SEARCH_ADS_CTR,     DIM),
        ("Web display avg",      WEB_DISPLAY_CTR,    DIM),
    ]
    for label, pct, color in bmarks:
        b = bar(min(pct / 5, 1.0), width=16)
        print(f"  {label:22}  {color}{pct:.2f}%{RESET}  {DIM}[{b}]{RESET}")

    conn.close()

    # ── Earnings & referral summary ────────────────────────────────────────────
    ef = Path(__file__).parent / "earnings.json"
    cf = Path(__file__).parent / "config.json"
    try:
        earnings = json.loads(ef.read_text()) if ef.exists() else {}
        cfg      = json.loads(cf.read_text()) if cf.exists() else {}
        mc       = earnings.get("total_mc", 0)
        dollars  = mc / 100_000
        hit      = earnings.get("milestone_hit", False)
        code     = cfg.get("referral_code")
        if mc > 0 or code:
            print()
            print(f"  {DIM}── Earnings ─────────────────────────────────{RESET}")
            if mc > 0:
                payout_mc  = 1_000_000   # $10 payout threshold
                pct_done   = min(mc / payout_mc, 1.0)
                b          = bar(pct_done, width=20)
                print(f"  Total earned:  {GREEN}{BOLD}${dollars:.4f}{RESET}", end="")
                if hit:
                    print(f"  {GREEN}(referral bonuses unlocked){RESET}")
                else:
                    remaining = max(0, (10.00 - dollars))
                    print(f"  (${remaining:.2f} to $10 payout)")
                print(f"  [{b}] {int(pct_done * 100)}% to first payout")
            if code:
                print(f"  Referral code: {BOLD}{code}{RESET}")
                print(f"  {DIM}python3 ~/.claude/ads/referral.py  — full referral stats{RESET}")
    except Exception:
        pass

    print()


if __name__ == "__main__":
    main()
