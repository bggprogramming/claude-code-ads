#!/usr/bin/env python3
"""
Ad analytics dashboard — run directly or ask Claude to run it.
"""
import sqlite3
from pathlib import Path

DB_FILE = Path(__file__).parent / "analytics.db"


def main():
    if not DB_FILE.exists():
        print("No analytics data yet. Run ad.py first.")
        return

    conn = sqlite3.connect(DB_FILE)

    print("\n╔══════════════════════════════════════╗")
    print("║         Ad Analytics Dashboard       ║")
    print("╚══════════════════════════════════════╝\n")

    rows = conn.execute("""
        SELECT
            ad_id,
            ad_text,
            COUNT(*) FILTER (WHERE event = 'impression') AS impressions,
            COUNT(*) FILTER (WHERE event = 'click')      AS clicks,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE event = 'click') /
                MAX(1, COUNT(*) FILTER (WHERE event = 'impression')), 2
            ) AS ctr_pct
        FROM events
        GROUP BY ad_id, ad_text
        ORDER BY impressions DESC
    """).fetchall()

    if not rows:
        print("No events recorded yet.")
        conn.close()
        return

    for ad_id, ad_text, impressions, clicks, ctr in rows:
        bar_len = min(int(impressions / max(r[2] for r in rows) * 20), 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {ad_id}")
        print(f"  {ad_text}")
        print(f"  [{bar}] {impressions} impressions · {clicks} clicks · {ctr}% CTR")
        print()

    totals = conn.execute("""
        SELECT
            COUNT(*) FILTER (WHERE event = 'impression') AS total_impressions,
            COUNT(*) FILTER (WHERE event = 'click')      AS total_clicks
        FROM events
    """).fetchone()

    print(f"  Total: {totals[0]} impressions · {totals[1]} clicks")
    conn.close()


if __name__ == "__main__":
    main()
