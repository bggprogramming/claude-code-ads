#!/usr/bin/env python3
"""
Funnel instrumentation — fire-and-forget lifecycle events so the onboarding/
earning/referral funnel can be measured (see funnel_summary view).

Pseudonymous: sends only the referral_code + a step name (+ optional small meta).
Never raises; never blocks the caller meaningfully.

Use:
  import funnel; funnel.log("registered")
  python3 funnel.py installed          # CLI form (used by install.sh)
"""
import json
import ssl
import sys
import threading
import urllib.request
from pathlib import Path

import certifi

BASE    = Path(__file__).parent
CFG     = BASE / "config.json"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def log(step, meta=None):
    try:
        cfg = json.loads(CFG.read_text())
    except Exception:
        cfg = {}
    url, key = cfg.get("supabase_url"), cfg.get("supabase_key")
    if not (url and key):
        return
    payload = json.dumps({
        "code": cfg.get("referral_code"),
        "step": str(step)[:40],
        "meta": meta or {},
    }).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/funnel_events",
        data=payload,
        headers={
            "apikey":        key,
            "Authorization": f"Bearer {key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
        },
        method="POST",
    )

    def _go():
        try:
            urllib.request.urlopen(req, timeout=4, context=SSL_CTX)
        except Exception:
            pass

    t = threading.Thread(target=_go, daemon=True)
    t.start()
    t.join(timeout=4)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        log(sys.argv[1])
