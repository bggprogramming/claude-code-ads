#!/usr/bin/env python3
"""
End-to-end test for earnings milestone notifications.

Tests:
  1. pending_notifications() returns nothing when total_mc is 0
  2. After crossing $0.01, the first_cent notification fires once
  3. Calling again returns nothing (already marked seen)
  4. After crossing $1.00, the one_dollar notification fires
  5. After crossing $5.00, the five_dollars notification fires
  6. After crossing $10.00, the ten_dollars notification fires
  7. Total: 4 notifications across 4 milestones, each fires exactly once
  8. track() still fires the Supabase milestone at $5 (milestone_hit flag)

Run: python3 ~/.claude/ads/test_notifications.py
"""
import json
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# We need to patch earnings.EARNINGS_FILE before importing
import earnings as _e

SEP = "  " + "─" * 52


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    suffix = f"  →  {detail}" if detail else ""
    print(f"  [{mark}] {label}{suffix}")
    return condition


def run_with_temp_earnings(initial_state, fn):
    """Run fn() with a temporary earnings.json, return (result, final_state)."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(initial_state, f)
        tmp_path = Path(f.name)

    original = _e.EARNINGS_FILE
    try:
        _e.EARNINGS_FILE = tmp_path
        result = fn()
        final  = json.loads(tmp_path.read_text())
        return result, final
    finally:
        _e.EARNINGS_FILE = original
        tmp_path.unlink(missing_ok=True)


def main():
    results = []

    print()
    print("  Earnings milestone notifications — E2E test")
    print(SEP)

    # ── Test 1: No notifications when mc == 0 ────────────────────────────────
    print()
    print("  Test 1 — No notifications below any threshold")
    print()

    notes, state = run_with_temp_earnings({"total_mc": 0, "milestone_hit": False}, _e.pending_notifications)
    results.append(check("pending_notifications() returns [] when mc=0",
                         notes == [], f"got {notes!r}"))

    # ── Test 2: first_cent fires at 1,000 mc ─────────────────────────────────
    print()
    print("  Test 2 — first_cent notification at $0.01")
    print()

    notes, state = run_with_temp_earnings({"total_mc": 1_000, "milestone_hit": False}, _e.pending_notifications)
    results.append(check("first_cent notification fires at 1,000 mc",
                         len(notes) == 1, f"{len(notes)} notification(s)"))
    results.append(check("first_cent message contains 'First ad'",
                         any("First ad" in n for n in notes), f"{notes!r}"))
    results.append(check("'first_cent' key stored in notified set",
                         "first_cent" in state.get("notified", []), f"notified={state.get('notified')}"))

    # ── Test 3: Idempotent — second call returns nothing ─────────────────────
    print()
    print("  Test 3 — Idempotent: calling again returns no duplicates")
    print()

    pre_state = {"total_mc": 1_000, "milestone_hit": False, "notified": ["first_cent"]}
    notes, _ = run_with_temp_earnings(pre_state, _e.pending_notifications)
    results.append(check("No notification when already in notified set",
                         notes == [], f"got {notes!r}"))

    # ── Test 4: one_dollar fires at 100,000 mc ───────────────────────────────
    print()
    print("  Test 4 — one_dollar notification at $1.00")
    print()

    pre_state = {"total_mc": 100_000, "milestone_hit": False, "notified": ["first_cent"]}
    notes, state = run_with_temp_earnings(pre_state, _e.pending_notifications)
    results.append(check("one_dollar notification fires at 100,000 mc",
                         len(notes) == 1, f"{len(notes)} notification(s)"))
    results.append(check("one_dollar message contains '$1.00'",
                         any("$1.00" in n for n in notes), f"{notes!r}"))
    results.append(check("'one_dollar' added to notified set",
                         "one_dollar" in state.get("notified", []), f"notified={state.get('notified')}"))

    # ── Test 5: five_dollars fires at 500,000 mc ─────────────────────────────
    print()
    print("  Test 5 — five_dollars notification at $5.00")
    print()

    pre_state = {
        "total_mc": 500_000, "milestone_hit": False,
        "notified": ["first_cent", "one_dollar"],
    }
    notes, state = run_with_temp_earnings(pre_state, _e.pending_notifications)
    results.append(check("five_dollars notification fires at 500,000 mc",
                         len(notes) == 1, f"{len(notes)} notification(s)"))
    results.append(check("five_dollars message contains '$5.00'",
                         any("$5.00" in n for n in notes), f"{notes!r}"))

    # ── Test 6: ten_dollars fires at 1,000,000 mc ────────────────────────────
    print()
    print("  Test 6 — ten_dollars notification at $10.00")
    print()

    pre_state = {
        "total_mc": 1_000_000, "milestone_hit": True,
        "notified": ["first_cent", "one_dollar", "five_dollars"],
    }
    notes, state = run_with_temp_earnings(pre_state, _e.pending_notifications)
    results.append(check("ten_dollars notification fires at 1,000,000 mc",
                         len(notes) == 1, f"{len(notes)} notification(s)"))
    results.append(check("ten_dollars message contains '$10.00'",
                         any("$10.00" in n for n in notes), f"{notes!r}"))

    # ── Test 7: All 4 fire at once if mc jumps from 0 → 1,000,000 ───────────
    print()
    print("  Test 7 — All 4 notifications fire when mc jumps from 0 to $10")
    print()

    notes, state = run_with_temp_earnings({"total_mc": 1_000_000, "milestone_hit": True},
                                          _e.pending_notifications)
    results.append(check("All 4 notifications fire at once",
                         len(notes) == 4, f"{len(notes)} notification(s)"))
    results.append(check("All 4 keys stored in notified",
                         set(state.get("notified", [])) == {"first_cent", "one_dollar", "five_dollars", "ten_dollars"},
                         str(state.get("notified"))))

    # ── Test 8: milestone_hit flag still works via track() ────────────────────
    print()
    print("  Test 8 — track() still sets milestone_hit at 500,000 mc")
    print()

    mock_ad = {"id": "test", "text": "test ad", "url": "https://example.com", "cpm": 20}

    # Start just below milestone, then add one spinner impression (50 mc each at $20 cpm → 1000 mc)
    # We need to be at 499_001 to cross at next impression
    just_below = {
        "total_mc": 499_000, "milestone_hit": False,
        "notified": ["first_cent", "one_dollar"],
        "imp_statusline": 0, "imp_spinner": 0,
    }

    def _track():
        # Add enough impressions to cross milestone
        for _ in range(2):
            _e.track(mock_ad, "statusline")   # each adds 2000 mc at $20 CPM
        return _e.load_earnings()

    _, final = run_with_temp_earnings(just_below, _track)
    results.append(check("milestone_hit becomes True when crossing 500,000 mc",
                         final.get("milestone_hit") is True,
                         f"milestone_hit={final.get('milestone_hit')}  total_mc={final.get('total_mc')}"))

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    passed = sum(1 for r in results if r)
    total  = len(results)
    print(SEP)
    print()
    if passed == total:
        print(f"  All {total} checks passed. Milestone notifications are working correctly.")
    else:
        print(f"  {passed}/{total} checks passed — see FAIL lines above.")
    print()

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
