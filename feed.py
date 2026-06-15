#!/usr/bin/env python3
"""
Remote ad feed loader with daily local cache and local fallback.

Priority:
  1. /tmp daily cache (avoids network on every statusLine call)
  2. GitHub raw feed (2s timeout — must not stall the status bar)
  3. Local ads.json bundled at install time
"""
import json
import ssl
import urllib.request
from datetime import date
from pathlib import Path

import certifi

BASE     = Path(__file__).parent
ADS_FILE = BASE / "ads.json"
FEED_URL = "https://raw.githubusercontent.com/bggprogramming/claude-code-ads/main/ads.json"
_SSL_CTX  = ssl.create_default_context(cafile=certifi.where())
_REQUIRED = {"id", "text", "url"}


def load_ads() -> list:
    """Return ad list. Never raises — falls back to [] on total failure."""
    today = date.today().isoformat()
    cache = Path(f"/tmp/claude-ads-feed-{today}.json")

    # 1. Warm daily cache
    if cache.exists():
        try:
            ads = json.loads(cache.read_text())
            if _valid(ads):
                return ads
        except Exception:
            pass

    # 2. Remote feed (short timeout — statusLine must not stall)
    try:
        req  = urllib.request.Request(FEED_URL, headers={"User-Agent": "claude-code-ads/1.0"})
        data = urllib.request.urlopen(req, timeout=2, context=_SSL_CTX).read()
        ads  = json.loads(data)
        if _valid(ads):
            try:
                cache.write_text(data.decode())
            except Exception:
                pass
            return ads
    except Exception:
        pass

    # 3. Bundled local file
    try:
        with open(ADS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _valid(ads) -> bool:
    return isinstance(ads, list) and bool(ads) and all(_REQUIRED.issubset(a.keys()) for a in ads)
