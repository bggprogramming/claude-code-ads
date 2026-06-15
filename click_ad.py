#!/usr/bin/env python3
"""
Prints a clickable OSC 8 ad link directly to /dev/tty after each Claude response.
Called by the Stop hook (non-async) so output lands in the terminal scrollback
buffer — outside Claude Code's TUI, where clicking actually works.

In iTerm2 / Warp / Ghostty: click the link to open.
In standard Terminal.app: cmd+click.
"""
import json
import os
import random
import sys
import urllib.parse
from pathlib import Path

BASE        = Path(__file__).parent
ADS_FILE    = BASE / "ads.json"
CLICK_PORT  = 54323
SESSION_CAP = 3

_sid         = os.environ.get("TERM_SESSION_ID") or os.environ.get("TMUX_PANE") or str(os.getppid())
SESSION_FILE = Path(f"/tmp/claude-ads-{_sid}.json")


def session_counts():
    try:
        return json.loads(SESSION_FILE.read_text()) if SESSION_FILE.exists() else {}
    except Exception:
        return {}


def weighted_sample(pool):
    total = sum(a.get("weight", 1) for a in pool)
    r = random.random() * total
    for ad in pool:
        r -= ad.get("weight", 1)
        if r <= 0:
            return ad
    return pool[-1]


def select_ad(ads):
    counts   = session_counts()
    eligible = [a for a in ads if counts.get(a["id"], 0) < SESSION_CAP]
    return weighted_sample(eligible or ads)


def osc8(text, url):
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def main():
    try:
        ads = json.loads(ADS_FILE.read_text())
    except Exception:
        sys.exit(0)
    if not ads:
        sys.exit(0)

    ad      = select_ad(ads)
    encoded = urllib.parse.quote(ad["url"], safe="")
    track   = f"http://127.0.0.1:{CLICK_PORT}/click?ad_id={ad['id']}&dest={encoded}"

    # Wrap the whole ad text in an OSC 8 hyperlink
    link = osc8(ad["text"], track)

    # Dim styling so it's visible but unobtrusive
    line = f"\033[2m{link}\033[0m\n"

    # Write to /dev/tty — bypasses Claude Code's TUI and lands directly in
    # the terminal where OSC 8 links are clickable
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(line)
            tty.flush()
    except Exception:
        # /dev/tty unavailable (e.g. CI) — fall back to stdout
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            pass


if __name__ == "__main__":
    main()
