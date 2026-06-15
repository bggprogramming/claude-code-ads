#!/usr/bin/env python3
"""Tests for completion_ad.py — 78-char separator line and elapsed-time logic."""
import json
import sys
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import completion_ad as _ca


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
        return True
    except AssertionError as e:
        print(f"  FAIL  {name}: {e}")
        return False


AD_CURSOR = {
    "id": "ad_cursor",
    "text": "✦ Cursor — AI pair programmer. cursor.com",
    "url": "https://cursor.com",
    "cpm": 25,
    "completion_text": "─── Sponsored by Cursor · AI pair programmer · cursor.com ────",
}

AD_NO_COMPLETION = {
    "id": "ad_linear",
    "text": "✦ Linear — Issue tracking. linear.app",
    "url": "https://linear.app",
    "cpm": 30,
}


# ── Line formatting tests ─────────────────────────────────────────────────────

def test_line_is_78_chars_with_completion_text():
    line = _ca.format_completion_line(AD_CURSOR)
    assert len(line) == 78, f"expected 78, got {len(line)}: {line!r}"

def test_line_is_78_chars_with_derived_text():
    line = _ca.format_completion_line(AD_NO_COMPLETION)
    assert len(line) == 78, f"expected 78, got {len(line)}: {line!r}"

def test_line_starts_with_dash():
    line = _ca.format_completion_line(AD_CURSOR)
    assert line.startswith("─"), f"should start with ─, got {line[:3]!r}"

def test_line_ends_with_dash():
    line = _ca.format_completion_line(AD_CURSOR)
    assert line.endswith("─"), f"should end with ─, got {line[-3:]!r}"

def test_line_contains_ad_content():
    line = _ca.format_completion_line(AD_CURSOR)
    # completion_text inner content (stripped of dashes) should appear
    assert "Cursor" in line, f"'Cursor' not found in {line!r}"

def test_derived_line_contains_ad_text_content():
    line = _ca.format_completion_line(AD_NO_COMPLETION)
    assert "linear.app" in line.lower() or "Linear" in line or "linear" in line.lower(), \
        f"ad content not found in {line!r}"

def test_short_inner_text_still_78_chars():
    ad = {"id": "x", "text": "Hi", "url": "https://x.com", "completion_text": "Hi"}
    line = _ca.format_completion_line(ad)
    assert len(line) == 78, f"expected 78, got {len(line)}"

def test_exactly_78_char_input_stays_78():
    # inner = " " + "A"*74 + " " = 76 chars → with 1 dash each side = 78
    inner_content = "A" * 74
    ad = {"id": "x", "text": inner_content, "url": "https://x.com",
          "completion_text": inner_content}
    line = _ca.format_completion_line(ad)
    assert len(line) == 78, f"expected 78, got {len(line)}"


# ── Elapsed-time tests ────────────────────────────────────────────────────────

def test_elapsed_returns_none_when_no_file():
    elapsed = _ca.elapsed_since_tool_start("session_that_does_not_exist_xyz")
    assert elapsed is None, f"expected None, got {elapsed}"

def test_elapsed_returns_seconds_when_file_present():
    with tempfile.TemporaryDirectory() as tmp:
        sid  = "testsession123"
        safe = "testsession123"
        tool_file = Path(tmp) / f"claude-ads-tool-start-{safe}.json"
        start_ts = time.time() - 45  # pretend tool started 45s ago
        tool_file.write_text(json.dumps({"ts": start_ts, "tool": "Bash"}))

        with patch.object(_ca, '_TOOL_START_DIR', tmp):
            elapsed = _ca.elapsed_since_tool_start(sid)

        assert elapsed is not None, "expected a float, got None"
        assert 44 < elapsed < 47, f"expected ~45s, got {elapsed}"

def test_elapsed_returns_none_on_corrupt_file():
    with tempfile.TemporaryDirectory() as tmp:
        sid = "badsession"
        tool_file = Path(tmp) / f"claude-ads-tool-start-{sid}.json"
        tool_file.write_text("not valid json {{{{")
        with patch.object(_ca, '_TOOL_START_DIR', tmp):
            elapsed = _ca.elapsed_since_tool_start(sid)
        assert elapsed is None


# ── CPM rate tests ────────────────────────────────────────────────────────────

def test_completion_surface_earns_200x_cpm():
    import earnings as _earnings
    mc = _earnings.impression_mc(AD_CURSOR, "completion")
    # cpm=25 → 25 * 200 = 5000 mc
    assert mc == 5000, f"expected 5000, got {mc}"

def test_completion_earns_more_than_statusline():
    import earnings as _earnings
    comp   = _earnings.impression_mc(AD_CURSOR, "completion")
    status = _earnings.impression_mc(AD_CURSOR, "statusline")
    assert comp > status, f"completion ({comp}) should beat statusline ({status})"

def test_completion_earns_more_than_spinner():
    import earnings as _earnings
    comp    = _earnings.impression_mc(AD_CURSOR, "completion")
    spinner = _earnings.impression_mc(AD_CURSOR, "spinner")
    assert comp > spinner, f"completion ({comp}) should beat spinner ({spinner})"


# ── Threshold constant ────────────────────────────────────────────────────────

def test_threshold_is_30_seconds():
    assert _ca.THRESHOLD == 30, f"expected THRESHOLD=30, got {_ca.THRESHOLD}"

def test_width_is_78():
    assert _ca.WIDTH == 78, f"expected WIDTH=78, got {_ca.WIDTH}"


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("line is 78 chars (completion_text)",         test_line_is_78_chars_with_completion_text),
        ("line is 78 chars (derived text)",            test_line_is_78_chars_with_derived_text),
        ("line starts with ─",                         test_line_starts_with_dash),
        ("line ends with ─",                           test_line_ends_with_dash),
        ("line contains ad content",                   test_line_contains_ad_content),
        ("derived line contains ad text",              test_derived_line_contains_ad_text_content),
        ("short inner text → still 78",                test_short_inner_text_still_78_chars),
        ("long input → still 78",                      test_exactly_78_char_input_stays_78),
        ("elapsed → None when no file",                test_elapsed_returns_none_when_no_file),
        ("elapsed → seconds when file present",        test_elapsed_returns_seconds_when_file_present),
        ("elapsed → None on corrupt file",             test_elapsed_returns_none_on_corrupt_file),
        ("completion surface = 200× CPM",              test_completion_surface_earns_200x_cpm),
        ("completion > statusline",                    test_completion_earns_more_than_statusline),
        ("completion > spinner",                       test_completion_earns_more_than_spinner),
        ("THRESHOLD = 30",                             test_threshold_is_30_seconds),
        ("WIDTH = 78",                                 test_width_is_78),
    ]

    print(f"\ntest_completion_ad.py — {len(tests)} tests\n")
    results = [run(name, fn) for name, fn in tests]
    passed  = sum(results)
    failed  = len(results) - passed
    print(f"\n{passed}/{len(results)} PASS", "✓" if not failed else f"  {failed} FAIL")
    sys.exit(0 if not failed else 1)
