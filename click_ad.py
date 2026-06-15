#!/usr/bin/env python3
"""
Prints a clickable OSC 8 ad link directly to /dev/tty after each Claude response.
Called by the Stop hook (non-async) so output lands in the terminal scrollback
buffer — outside Claude Code's TUI, where clicking actually works.

Also checks for earnings milestones and prints a celebration line immediately
after the ad when one is crossed.

In iTerm2 / Warp / Ghostty: click the link to open.
In standard Terminal.app: cmd+click.
"""
import json
import os
import sys
import urllib.parse
from pathlib import Path

BASE        = Path(__file__).parent
CLICK_PORT  = 54323
SESSION_CAP = 3

_sid         = os.environ.get("TERM_SESSION_ID") or os.environ.get("TMUX_PANE") or str(os.getppid())
SESSION_FILE = Path(f"/tmp/claude-ads-{_sid}.json")

sys.path.insert(0, str(BASE))
import feed    as _feed
import earnings as _earnings


def session_counts():
    try:
        return json.loads(SESSION_FILE.read_text()) if SESSION_FILE.exists() else {}
    except Exception:
        return {}


def select_ad(ads):
    import random
    counts   = session_counts()
    eligible = [a for a in ads if counts.get(a["id"], 0) < SESSION_CAP]
    pool     = eligible or ads
    total    = sum(a.get("weight", 1) for a in pool)
    r        = random.random() * total
    for ad in pool:
        r -= ad.get("weight", 1)
        if r <= 0:
            return ad
    return pool[-1]


def osc8(text, url):
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def main():
    ads = _feed.load_ads()
    if not ads:
        sys.exit(0)

    ad      = select_ad(ads)
    encoded = urllib.parse.quote(ad["url"], safe="")
    track   = f"http://127.0.0.1:{CLICK_PORT}/click?ad_id={ad['id']}&dest={encoded}"
    link    = osc8(ad["text"], track)
    ad_line = f"\033[2m{link}\033[0m\n"

    # Milestone notifications (show at most once each, immediately after the ad)
    notifications = _earnings.pending_notifications()

    try:
        with open("/dev/tty", "w") as tty:
            tty.write(ad_line)
            for msg in notifications:
                tty.write(f"{msg}\n")
            tty.flush()
    except Exception:
        try:
            sys.stdout.write(ad_line)
            for msg in notifications:
                sys.stdout.write(f"{msg}\n")
            sys.stdout.flush()
        except Exception:
            pass


if __name__ == "__main__":
    main()
