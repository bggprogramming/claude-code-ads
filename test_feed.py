#!/usr/bin/env python3
"""
End-to-end test for the remote ad feed loader (feed.py).

Tests:
  1. load_ads() returns a non-empty list
  2. Each ad has the required fields (id, text, url)
  3. Remote fetch succeeds and cache file is created
  4. Second call reads from cache (no second network request)
  5. Cache is valid JSON with correct structure
  6. Graceful fallback when given a bad URL (monkey-patched)
  7. Local ads.json fallback works when remote is unavailable
  8. Feed validation rejects malformed entries

Run: python3 ~/.claude/ads/test_feed.py
"""
import json
import sys
import tempfile
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import feed as _feed

SEP = "  " + "─" * 52
TODAY = date.today().isoformat()


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    suffix = f"  →  {detail}" if detail else ""
    print(f"  [{mark}] {label}{suffix}")
    return condition


def main():
    results = []

    print()
    print("  Remote ad feed — E2E test")
    print(SEP)

    # Clear today's cache so we test a real fetch
    cache_path = Path(f"/tmp/claude-ads-feed-{TODAY}.json")
    if cache_path.exists():
        cache_path.unlink()

    # ── Test 1 & 2: load_ads() returns valid ads ──────────────────────────────
    print()
    print("  Test 1/2 — load_ads() returns valid ad list")
    print()

    ads = _feed.load_ads()
    results.append(check("load_ads() returns non-empty list",
                         isinstance(ads, list) and len(ads) > 0, f"{len(ads)} ads"))

    required = {"id", "text", "url"}
    all_valid = all(required.issubset(a.keys()) for a in ads)
    results.append(check("All ads have required fields (id, text, url)",
                         all_valid,
                         "ok" if all_valid else f"missing fields in some ads"))

    # ── Test 3: Cache file was created ────────────────────────────────────────
    print()
    print("  Test 3 — Daily cache file created after fetch")
    print()

    cache_available = cache_path.exists()
    results.append(check("Cache file exists at /tmp/claude-ads-feed-{today}.json",
                         cache_available,
                         str(cache_path) if cache_available else "remote unreachable (local fallback used)"))

    if cache_available:
        cached = json.loads(cache_path.read_text())
        results.append(check("Cached file contains valid ad list",
                             isinstance(cached, list) and len(cached) > 0,
                             f"{len(cached)} ads"))
    else:
        results.append(check("Cache content check skipped (remote unavailable)", True, "SKIP"))

    # ── Test 4: Second call hits cache (no network) ───────────────────────────
    print()
    print("  Test 4 — Second call returns from cache")
    print()

    if cache_path.exists():
        import urllib.request as _req
        call_count = [0]
        real_urlopen = _req.urlopen
        def counting_urlopen(*args, **kwargs):
            call_count[0] += 1
            return real_urlopen(*args, **kwargs)

        with patch.object(_req, 'urlopen', side_effect=counting_urlopen):
            ads2 = _feed.load_ads()

        results.append(check("No network call on second load (cache hit)",
                             call_count[0] == 0,
                             f"{call_count[0]} network call(s) made"))
        results.append(check("Second load returns same ads",
                             len(ads2) == len(ads),
                             f"{len(ads2)} vs {len(ads)}"))
    else:
        # Remote was unavailable — skip cache-hit test
        results.append(check("Cache hit test skipped (remote unavailable)", True, "SKIP"))
        results.append(check("Second load skipped", True, "SKIP"))

    # ── Test 5: Graceful fallback on bad URL ──────────────────────────────────
    print()
    print("  Test 5 — Falls back to local ads.json on network failure")
    print()

    # Clear cache so it tries the network
    if cache_path.exists():
        cache_path.unlink()

    original_url = _feed.FEED_URL
    try:
        _feed.FEED_URL = "https://invalid.example.invalid/ads.json"
        ads_fallback  = _feed.load_ads()
    finally:
        _feed.FEED_URL = original_url

    results.append(check("Returns non-empty list even when remote fails",
                         isinstance(ads_fallback, list) and len(ads_fallback) > 0,
                         f"{len(ads_fallback)} ads from fallback"))

    local_ads = json.loads((Path(__file__).parent / "ads.json").read_text())
    results.append(check("Fallback matches local ads.json content",
                         len(ads_fallback) == len(local_ads),
                         f"fallback={len(ads_fallback)} local={len(local_ads)}"))

    # Restore cache for next tests
    _feed.FEED_URL = original_url
    _feed.load_ads()

    # ── Test 6: _valid() rejects malformed entries ────────────────────────────
    print()
    print("  Test 6 — Feed validation rejects malformed entries")
    print()

    results.append(check("_valid([]) is False", not _feed._valid([]), "empty list"))
    results.append(check("_valid([{'id':'x'}]) is False (missing text, url)",
                         not _feed._valid([{"id": "x"}]), "missing fields"))
    results.append(check("_valid('string') is False", not _feed._valid("string"), "not a list"))
    results.append(check("_valid([{id, text, url}]) is True",
                         _feed._valid([{"id": "x", "text": "t", "url": "u"}]), "valid"))

    # ── Test 7: Cache integrity ───────────────────────────────────────────────
    print()
    print("  Test 7 — Cache file integrity")
    print()

    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text())
            results.append(check("Cache file is valid JSON",
                                 True, f"{len(data)} ads"))
            results.append(check("Cache content matches load_ads() output",
                                 data == _feed.load_ads(),
                                 "content matches"))
        except json.JSONDecodeError as e:
            results.append(check("Cache file is valid JSON", False, str(e)))
            results.append(check("Cache content matches", False, "skipped"))
    else:
        # Remote unavailable in this environment — verify local fallback is consistent
        ads_a = _feed.load_ads()
        ads_b = _feed.load_ads()
        results.append(check("Cache integrity skipped (remote unavailable)", True, "SKIP"))
        results.append(check("Repeated load_ads() returns same local fallback",
                             ads_a == ads_b, f"{len(ads_a)} ads consistent"))

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    passed = sum(1 for r in results if r)
    total  = len(results)
    print(SEP)
    print()
    if passed == total:
        print(f"  All {total} checks passed. Remote ad feed is working correctly.")
    else:
        print(f"  {passed}/{total} checks passed — see FAIL lines above.")
    print()

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
