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
import base64
import json
import os
import ssl
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path

import certifi

BASE        = Path(__file__).parent
CLICK_PORT  = 54323
SESSION_CAP = 3
SITE_BASE   = "https://bggprogramming.github.io/claude-code-ads"
SSL_CTX     = ssl.create_default_context(cafile=certifi.where())

_sid         = os.environ.get("TERM_SESSION_ID") or os.environ.get("TMUX_PANE") or str(os.getppid())
SESSION_FILE = Path(f"/tmp/claude-ads-{_sid}.json")

sys.path.insert(0, str(BASE))
import context     as _ctx
import earnings    as _earnings
import feed        as _feed
import viewability as _view


def track_scrollback(ad, ad_text, variant, cfg):
    """Count the post-response scrollback ad as an impression (server computes
    earnings). This is the primary surface in agents without a status line
    (e.g. Codex). Viewability-gated by the caller."""
    if not (cfg.get("supabase_url") and cfg.get("supabase_key")):
        return
    url = f"{cfg['supabase_url']}/functions/v1/track-event"
    payload = json.dumps({
        "ad_id":       ad["id"],
        "ad_text":     ad_text,
        "event":       "impression",
        "surface":     "scrollback",
        "user_id":     cfg.get("user_id"),
        "variant":     variant,
        "share_level": cfg.get("share_level", 0),
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "apikey":        cfg["supabase_key"],
        "Authorization": f"Bearer {cfg['supabase_key']}",
        "Content-Type":  "application/json",
    }, method="POST")
    t = threading.Thread(
        target=lambda: _safe_urlopen(req), daemon=True)
    t.start(); t.join(timeout=4)
    # Advance LOCAL earnings too, so the progress bar + milestones move — this is
    # the primary surface in agents without a status line (e.g. Codex).
    try:
        _earnings.track(ad, "scrollback")
    except Exception:
        pass


def _safe_urlopen(req):
    try:
        urllib.request.urlopen(req, timeout=4, context=SSL_CTX)
    except Exception:
        pass


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


def render_logo(ad):
    """
    Return a terminal representation of the advertiser's brand logo.

    1. iTerm2 / kitty: the real uploaded image, inline (crisp).
    2. Any other terminal (incl. Apple Terminal, VS Code/Cursor): the actual logo
       rendered as colored Unicode half-blocks — low-res but recognizable, using
       truecolor when available, else the 256-color cube.
    3. No logo / no Pillow / fetch fails: a small colored brand chip.
    Returns '' if there's nothing to show.
    """
    logo_url = ad.get("logo_url")
    term     = os.environ.get("TERM_PROGRAM", "")
    is_iterm = term == "iTerm.app"
    is_kitty = "kitty" in os.environ.get("TERM", "") or bool(os.environ.get("KITTY_WINDOW_ID"))

    data = None
    if logo_url:
        try:
            req  = urllib.request.Request(logo_url, headers={"User-Agent": "claude-code-ads/2.0"})
            data = urllib.request.urlopen(req, timeout=1.5, context=SSL_CTX).read()
            if not data or len(data) > 256 * 1024:
                data = None
        except Exception:
            data = None

    if data:
        b64 = base64.b64encode(data).decode()
        if is_iterm:
            return f"\033]1337;File=inline=1;preserveAspectRatio=1;height=2:{b64}\a "
        if is_kitty:
            return f"\033_Gf=100,a=T,t=d;{b64}\033\\ "
        art = _blocks_art(data)        # real logo as colored blocks (Apple Terminal etc.)
        if art:
            return art

    return _chip(ad)


def _blocks_art(data, cells_tall=6, max_wide=24):
    """Render image bytes as colored half-block art (▀: fg=top px, bg=bottom px)."""
    try:
        import io
        from PIL import Image
    except Exception:
        return None
    try:
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        bgc = Image.new("RGBA", im.size, (11, 11, 13, 255))   # flatten alpha on terminal bg
        im  = Image.alpha_composite(bgc, im).convert("RGB")
        ph  = cells_tall * 2
        aspect = (im.width / im.height) if im.height else 1.0
        pw  = max(2, min(max_wide, round(ph * aspect)))
        im  = im.resize((pw, ph))
        px  = im.load()
        truecolor = os.environ.get("COLORTERM", "") in ("truecolor", "24bit")

        def code(rgb, fg):
            r, g, b = rgb
            lead = 38 if fg else 48
            if truecolor:
                return f"\033[{lead};2;{r};{g};{b}m"
            n = 16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)
            return f"\033[{lead};5;{n}m"

        lines = []
        for cy in range(cells_tall):
            line = "  "
            for x in range(pw):
                top = px[x, cy * 2]
                bot = px[x, cy * 2 + 1]
                line += code(top, True) + code(bot, False) + "▀"
            lines.append(line + "\033[0m")
        return "\n".join(lines) + "\n"
    except Exception:
        return None


def _chip(ad):
    label = ""
    for ch in ad.get("text", ""):
        if ch.isalnum():
            label = ch.upper()
            break
    if not label:
        return ""
    palette = [39, 170, 213, 220, 48, 203, 141]
    color = palette[sum(ord(c) for c in ad.get("id", "x")) % len(palette)]
    return f"\033[48;5;{color}m\033[38;5;232m {label} \033[0m "


_GOAL_LADDER = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]


def earnings_progress_line(cfg):
    """A compact earnings bar shown after every response, with a rolling goal."""
    state = _earnings.load_earnings()
    total_imp = (
        state.get("imp_statusline", 0)
        + state.get("imp_spinner", 0)
        + state.get("imp_completion", 0)
        + state.get("imp_scrollback", 0)
        + state.get("imp_vscode_statusbar", 0)
    )
    if total_imp == 0:
        return None

    mc      = state.get("total_mc", 0)
    dollars = mc / 100_000
    # Next goal = smallest ladder tier above current earnings (always something to chase).
    target  = next((t for t in _GOAL_LADDER if t > dollars), None)
    if target is None:
        target = (int(dollars / 1000) + 1) * 1000
    pct     = min(dollars / target, 1.0)
    filled  = int(pct * 12)
    bar     = "▓" * filled + "░" * (12 - filled)
    code    = cfg.get("referral_code", "")
    ref_url = f"{SITE_BASE}/?ref={code}" if code else SITE_BASE

    line = (
        f"\033[2m[claude-code-ads]\033[0m \033[38;5;156m${dollars:.2f}\033[0m"
        f" \033[2m[{bar}] ${target:g} · share: {ref_url}\033[0m"
    )

    # Nudge: if not at the top earnings tier, show the concrete upside (drives opt-in).
    lvl = int(cfg.get("share_level", 0))
    if lvl < 3:
        share_mult = [1.0, 1.3, 1.7, 2.5]
        per1k = (mc / total_imp / 100) if total_imp else 0.0
        extra = per1k * (2.5 / share_mult[max(0, min(3, lvl))] - 1) if per1k else 0.0
        upside = f"≈ +${extra:,.2f}/1k" if extra > 0 else "up to 2.5×"
        line += (f"\n\033[2m  └ \033[0m\033[38;5;205m{upside} more at Max\033[0m"
                 f"\033[2m → \033[0m\033[38;5;156mpython3 ~/.claude/ads/optin.py\033[0m")
    return line


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
    logo     = render_logo(ad)
    ad_line  = f"{logo}\033[2m{link}\033[0m\n"

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

    # Count the scrollback ad as an impression only if the window is visible.
    if _view.is_viewable():
        track_scrollback(ad, ad_text, _variant, cfg)


if __name__ == "__main__":
    main()
