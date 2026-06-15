#!/usr/bin/env python3
"""
Prints a clickable OSC 8 ad link directly to /dev/tty after each Claude response.
Called by the Stop hook (non-async) so output lands in the terminal scrollback
buffer — outside Claude Code's TUI, where clicking actually works.

Also:
  - Checks for earnings milestones and prints a celebration line
  - Every 50 impressions, prints a progress bar towards first payout
  - Uses copy variants selected by detected project context
"""
import json
import os
import sys
import urllib.parse
from pathlib import Path

BASE        = Path(__file__).parent
CLICK_PORT  = 54323
SESSION_CAP = 3
SITE_BASE   = "https://bggprogramming.github.io/claude-code-ads"

_sid         = os.environ.get("TERM_SESSION_ID") or os.environ.get("TMUX_PANE") or str(os.getppid())
SESSION_FILE = Path(f"/tmp/claude-ads-{_sid}.json")

sys.path.insert(0, str(BASE))
import context  as _ctx
import earnings as _earnings
import feed     as _feed


def load_config():
    try:
        with open(BASE / "config.json") as f:
            return json.load(f)
    except Exception:
        return {}


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


def earnings_progress_line(cfg):
    """Return a progress bar line every 50 total impressions, or None."""
    state = _earnings.load_earnings()
    total_imp = (
        state.get("imp_statusline", 0)
        + state.get("imp_spinner", 0)
        + state.get("imp_completion", 0)
        + state.get("imp_vscode_statusbar", 0)
    )
    if total_imp == 0 or total_imp % 50 != 0:
        return None

    mc       = state.get("total_mc", 0)
    dollars  = mc / 100_000
    payout   = 10.0
    pct      = min(mc / 1_000_000, 1.0)
    filled   = int(pct * 10)
    bar      = "▓" * filled + "░" * (10 - filled)
    code     = cfg.get("referral_code", "")
    ref_url  = f"{SITE_BASE}/?ref={code}" if code else SITE_BASE

    return (
        f"\033[2m[claude-code-ads] [{bar}] ${dollars:.2f} / ${payout:.2f}"
        f" · share: {ref_url}\033[0m"
    )


def main():
    # Read hook stdin for context (Stop hook passes session_id, cwd)
    data = {}
    try:
        raw = sys.stdin.read(4096)
        if raw.strip():
            data = json.loads(raw)
    except Exception:
        pass

    session_id = data.get("session_id") or _sid
    hook_cwd   = data.get("cwd")

    ads = _feed.load_ads()
    if not ads:
        sys.exit(0)

    cfg          = load_config()
    context_tags = _ctx.get_context(cwd=hook_cwd, session_id=session_id)
    ad           = select_ad(ads)
    ad_text, _variant = _ctx.select_copy(ad, context_tags)

    encoded  = urllib.parse.quote(ad["url"], safe="")
    track    = f"http://127.0.0.1:{CLICK_PORT}/click?ad_id={ad['id']}&dest={encoded}"
    link     = osc8(ad_text, track)
    ad_line  = f"\033[2m{link}\033[0m\n"

    # Milestone notifications (each fires exactly once)
    notifications = _earnings.pending_notifications()

    # Earnings progress bar (every 50 impressions)
    progress = earnings_progress_line(cfg)

    try:
        with open("/dev/tty", "w") as tty:
            tty.write(ad_line)
            for msg in notifications:
                tty.write(f"{msg}\n")
            if progress:
                tty.write(f"{progress}\n")
            tty.flush()
    except Exception:
        try:
            sys.stdout.write(ad_line)
            for msg in notifications:
                sys.stdout.write(f"{msg}\n")
            if progress:
                sys.stdout.write(f"{progress}\n")
            sys.stdout.flush()
        except Exception:
            pass


if __name__ == "__main__":
    main()
