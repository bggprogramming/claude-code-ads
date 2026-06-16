#!/usr/bin/env python3
"""
Ad feed loader.

Primary source is the ad-feed edge function, which merges built-in house ads with
live PAID advertiser campaigns ordered by bid (the auction). This replaces the old
"edit ads.json on every machine" model — new advertisers appear on all clients
within one short cache window.

Priority:
  1. Short-lived /tmp cache (avoids a network call on every statusLine render)
  2. ad-feed edge function (authoritative; bid-ordered; integrity-hashed)
  3. Legacy GitHub raw ads.json
  4. Local ads.json bundled at install time
"""
import hashlib
import json
import ssl
import time
import urllib.request
from pathlib import Path

import certifi

BASE      = Path(__file__).parent
ADS_FILE  = BASE / "ads.json"
CFG_FILE  = BASE / "config.json"
GITHUB_URL = "https://raw.githubusercontent.com/bggprogramming/mango/main/ads.json"
CACHE_FILE = Path("/tmp/mango-feed.json")
CACHE_TTL  = 60           # seconds — snappy for the live auction, cheap enough for the status bar
_SSL_CTX   = ssl.create_default_context(cafile=certifi.where())
_REQUIRED  = {"id", "text", "url"}


def _feed_fn_url() -> str:
    try:
        base = json.loads(CFG_FILE.read_text())["supabase_url"].rstrip("/")
        return f"{base}/functions/v1/ad-feed"
    except Exception:
        return ""


def _verify_hash(ads, expected) -> bool:
    """Best-effort integrity check of the fetched payload (matches the edge
    function's JSON.stringify(ads))."""
    if not expected:
        return True
    try:
        canon = json.dumps(ads, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canon.encode()).hexdigest() == expected
    except Exception:
        return True   # never block serving on a hashing hiccup


def load_ads() -> list:
    """Return ad list. Never raises — falls back to [] on total failure."""
    # 1. Warm short-lived cache
    try:
        if CACHE_FILE.exists() and (time.time() - CACHE_FILE.stat().st_mtime) < CACHE_TTL:
            ads = json.loads(CACHE_FILE.read_text())
            if _valid(ads):
                return ads
    except Exception:
        pass

    # 2. ad-feed edge function (auction-ordered, authoritative)
    fn_url = _feed_fn_url()
    if fn_url:
        try:
            req  = urllib.request.Request(fn_url, headers={"User-Agent": "mango/2.0"})
            raw  = urllib.request.urlopen(req, timeout=2, context=_SSL_CTX).read()
            body = json.loads(raw)
            ads  = body.get("ads") if isinstance(body, dict) else body
            if _valid(ads) and _verify_hash(ads, body.get("hash") if isinstance(body, dict) else None):
                try:
                    CACHE_FILE.write_text(json.dumps(ads))
                except Exception:
                    pass
                return ads
        except Exception:
            pass

    # 3. Legacy GitHub raw feed
    try:
        req  = urllib.request.Request(GITHUB_URL, headers={"User-Agent": "mango/2.0"})
        data = urllib.request.urlopen(req, timeout=2, context=_SSL_CTX).read()
        ads  = json.loads(data)
        if _valid(ads):
            return ads
    except Exception:
        pass

    # 4. Bundled local file
    try:
        with open(ADS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _valid(ads) -> bool:
    return isinstance(ads, list) and bool(ads) and all(_REQUIRED.issubset(a.keys()) for a in ads)
