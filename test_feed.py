#!/usr/bin/env python3
"""
End-to-end test for the ad feed loader (feed.py).

feed.py now fetches the ad-feed edge function (built-in house ads + live auction
campaigns, bid-ordered, integrity-hashed), with a short /tmp cache and a
GitHub-raw → local ads.json fallback chain.

Tests:
  1/2. load_ads() returns a valid non-empty list
  3.   Cache file is created after a fetch
  4.   Second call (within TTL) hits the cache — no network
  5.   Falls back to local ads.json when the function + GitHub are unreachable
  6.   _valid() rejects malformed entries
  7.   _verify_hash() accepts a matching hash and rejects a bad one

Run: python3 ~/.claude/ads/test_feed.py
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import feed as _feed

SEP = "  " + "─" * 52
CACHE = _feed.CACHE_FILE


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  →  {detail}" if detail else ""))
    return condition


def main():
    results = []
    print()
    print("  Ad feed loader — E2E test")
    print(SEP)

    if CACHE.exists():
        CACHE.unlink()

    # ── 1/2: valid ad list ────────────────────────────────────────────────────
    print("\n  Test 1/2 — load_ads() returns valid ad list\n")
    ads = _feed.load_ads()
    results.append(check("load_ads() returns non-empty list",
                         isinstance(ads, list) and len(ads) > 0, f"{len(ads)} ads"))
    required = {"id", "text", "url"}
    results.append(check("All ads have required fields (id, text, url)",
                         all(required.issubset(a.keys()) for a in ads), "ok"))

    # ── 3: cache created ──────────────────────────────────────────────────────
    print("\n  Test 3 — Cache file created after fetch\n")
    cache_ok = CACHE.exists()
    results.append(check(f"Cache file exists at {CACHE}", cache_ok,
                         str(CACHE) if cache_ok else "remote unreachable (local fallback used)"))
    if cache_ok:
        cached = json.loads(CACHE.read_text())
        results.append(check("Cached file is a valid ad list",
                             isinstance(cached, list) and len(cached) > 0, f"{len(cached)} ads"))
    else:
        results.append(check("Cache content check skipped", True, "SKIP"))

    # ── 4: second call hits cache (no network) ────────────────────────────────
    print("\n  Test 4 — Second call returns from cache (within TTL)\n")
    if cache_ok:
        import urllib.request as _req
        calls = [0]
        real = _req.urlopen
        def counting(*a, **k):
            calls[0] += 1
            return real(*a, **k)
        with patch.object(_req, "urlopen", side_effect=counting):
            ads2 = _feed.load_ads()
        results.append(check("No network call on cached second load", calls[0] == 0,
                             f"{calls[0]} network call(s)"))
        results.append(check("Second load returns same ads", len(ads2) == len(ads),
                             f"{len(ads2)} vs {len(ads)}"))
    else:
        results.append(check("Cache-hit test skipped", True, "SKIP"))
        results.append(check("Second load skipped", True, "SKIP"))

    # ── 5: fallback to local when function + GitHub fail ──────────────────────
    print("\n  Test 5 — Falls back to local ads.json when remote is unreachable\n")
    if CACHE.exists():
        CACHE.unlink()
    with patch.object(_feed, "_feed_fn_url", return_value="https://invalid.example.invalid/fn"), \
         patch.object(_feed, "GITHUB_URL", "https://invalid.example.invalid/ads.json"):
        ads_fb = _feed.load_ads()
    results.append(check("Returns non-empty list when remote fails",
                         isinstance(ads_fb, list) and len(ads_fb) > 0, f"{len(ads_fb)} ads"))
    local_ads = json.loads((Path(__file__).parent / "ads.json").read_text())
    results.append(check("Fallback matches local ads.json",
                         len(ads_fb) == len(local_ads), f"fallback={len(ads_fb)} local={len(local_ads)}"))

    # ── 6: validation ─────────────────────────────────────────────────────────
    print("\n  Test 6 — Feed validation rejects malformed entries\n")
    results.append(check("_valid([]) is False", not _feed._valid([]), "empty"))
    results.append(check("_valid([{'id':'x'}]) is False", not _feed._valid([{"id": "x"}]), "missing fields"))
    results.append(check("_valid('string') is False", not _feed._valid("string"), "not a list"))
    results.append(check("_valid([{id,text,url}]) is True",
                         _feed._valid([{"id": "x", "text": "t", "url": "u"}]), "valid"))

    # ── 7: integrity hash (#6 feed signing) ───────────────────────────────────
    print("\n  Test 7 — Payload integrity hash verification\n")
    import hashlib
    sample = [{"id": "a", "text": "t", "url": "u"}]
    good = hashlib.sha256(json.dumps(sample, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    results.append(check("_verify_hash accepts a matching hash", _feed._verify_hash(sample, good), "match"))
    results.append(check("_verify_hash rejects a wrong hash", not _feed._verify_hash(sample, "deadbeef"), "mismatch"))
    results.append(check("_verify_hash passes when no hash provided", _feed._verify_hash(sample, None), "no-op"))

    # restore a warm cache
    _feed.load_ads()

    print()
    passed = sum(1 for r in results if r)
    total  = len(results)
    print(SEP)
    print()
    print(f"  All {total} checks passed. Ad feed loader is working correctly."
          if passed == total else f"  {passed}/{total} checks passed — see FAIL lines above.")
    print()
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
