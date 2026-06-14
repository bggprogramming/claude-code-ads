#!/usr/bin/env python3
"""
Ad analytics dashboard — run directly or ask Claude to run it.
Shows impressions by surface (spinner / statusline), clicks, CTR per ad,
and referral earnings summary.
"""
import json
import sqlite3
from pathlib import Path

DB_FILE = Path(__file__).parent / "analytics.db"


def main():
    if not DB_FILE.exists():
        print("No analytics data yet. Run ad.py first.")
        return

    conn = sqlite3.connect(DB_FILE)

    print("\n╔══════════════════════════════════════════════╗")
    print("║           Ad Analytics Dashboard             ║")
    print("╚══════════════════════════════════════════════╝\n")

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
        print("  No events recorded yet.")
        conn.close()
        return

    max_imp = max(r[2] for r in rows) or 1
    for ad_id, ad_text, impressions, spinner, statusline, clicks, ctr in rows:
        bar_len = min(int(impressions / max_imp * 22), 22)
        bar     = "█" * bar_len + "░" * (22 - bar_len)
        print(f"  {ad_id}")
        print(f"  {ad_text[:60]}")
        print(f"  [{bar}] {impressions} impressions  ({spinner} spinner / {statusline} statusline)")
        print(f"  {clicks} clicks  ·  {ctr}% CTR")
        print()

    # ── Surface totals ─────────────────────────────────────────────────────────
    surfaces = conn.execute("""
        SELECT surface, COUNT(*) AS n
        FROM events
        GROUP BY surface
        ORDER BY n DESC
    """).fetchall()

    print("  ── By surface ──────────────────────────────")
    for surface, n in surfaces:
        print(f"  {(surface or 'unknown'):12}  {n}")

    # ── Grand totals ───────────────────────────────────────────────────────────
    totals = conn.execute("""
        SELECT
            COUNT(*) FILTER (WHERE event = 'impression') AS total_imp,
            COUNT(*) FILTER (WHERE event = 'click')      AS total_clicks
        FROM events
    """).fetchone()
    print(f"\n  Total: {totals[0]} impressions · {totals[1]} clicks")

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
            print("\n  ── Earnings ────────────────────────────────")
            if mc > 0:
                print(f"  Total earned:  ${dollars:.4f}", end="")
                if hit:
                    print("  (milestone hit!)")
                else:
                    remaining = max(0, (5.00 - dollars))
                    print(f"  (${remaining:.4f} to $5 milestone)")
            if code:
                print(f"  Referral code: {code}")
                print(f"  Run: python3 ~/.claude/ads/referral.py  for full referral stats")
    except Exception:
        pass


if __name__ == "__main__":
    main()
