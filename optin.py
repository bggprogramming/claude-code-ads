#!/usr/bin/env python3
"""
Earnings sharing — interactive tier picker (like Claude Code's effort slider).

The more context you share, the better advertisers can target you, the more they
bid, and the higher your earnings multiplier. "Max" is the fun, top-earning tier.

  Interactive:  python3 ~/.claude/ads/optin.py
  Set directly: python3 ~/.claude/ads/optin.py --level max     (or 0..3 / off)
  Status:       python3 ~/.claude/ads/optin.py --status
  Off:          python3 ~/.claude/ads/optin.py --disable

Stores `share_level` (0..3) in config.json. A Stop hook (context_uploader.py)
uploads only what the chosen tier permits; track-event applies the multiplier.
"""
import json
import sys
from pathlib import Path

BASE     = Path(__file__).parent
CFG_FILE = BASE / "config.json"
SETTINGS = Path.home() / ".claude" / "settings.json"
UPLOADER = str(BASE / "context_uploader.py")

# ── ANSI ──────────────────────────────────────────────────────────────────────
R   = "\033[0m"; B = "\033[1m"; DIM = "\033[2m"
WHITE  = "\033[97m"
GREY   = "\033[38;5;244m"
GREEN  = "\033[38;5;156m"   # money green (b4ff69-ish)
PURPLE = "\033[38;5;141m"   # "ultracode" purple
PINK   = "\033[38;5;205m"   # "max" magenta

# ── Tiers ───────────────────────────────────────────────────────────────────
TIERS = [
    {"key": "private", "name": "private", "mult": 1.0, "color": GREY,
     "tag": "Private",
     "desc": "Nothing leaves your machine — only that an ad was shown.\nYou still earn, just at the base rate."},
    {"key": "stack", "name": "stack", "mult": 1.3, "color": WHITE,
     "tag": "Stack",
     "desc": "Share your languages & tools (e.g. typescript, docker).\nAdvertisers can target you, so they bid more."},
    {"key": "context", "name": "context", "mult": 1.7, "color": WHITE,
     "tag": "Context",
     "desc": "+ project signals & file types for sharper targeting.\nHigher relevance → higher CPMs → more for you."},
    {"key": "max", "name": "max", "mult": 2.5, "color": PINK,
     "tag": "Max payout",
     "desc": "+ the gist of what you're building. Premium, hand-matched\ninventory. This is where the top earners run."},
]
DEFAULT_LEVEL = 1


def load_cfg():
    try: return json.loads(CFG_FILE.read_text())
    except Exception: return {}

def save_cfg(cfg):
    tmp = CFG_FILE.with_suffix(".tmp"); tmp.write_text(json.dumps(cfg, indent=2)); tmp.replace(CFG_FILE)

def load_settings():
    try: return json.loads(SETTINGS.read_text())
    except Exception: return {}

def save_settings(s):
    tmp = SETTINGS.with_suffix(".tmp"); tmp.write_text(json.dumps(s, indent=2)); tmp.replace(SETTINGS)


def _uploader_present(s):
    return any("context_uploader" in h.get("command", "")
               for m in s.get("hooks", {}).get("Stop", []) for h in m.get("hooks", []))

def _set_uploader(on):
    s = load_settings()
    if on and not _uploader_present(s):
        hook = {"type": "command", "command": f'python3 "{UPLOADER}"', "async": True}
        stop = s.setdefault("hooks", {}).setdefault("Stop", [])
        (stop[0].setdefault("hooks", []).append(hook) if stop else stop.append({"hooks": [hook]}))
        save_settings(s)
    elif not on and _uploader_present(s):
        for m in s.get("hooks", {}).get("Stop", []):
            m["hooks"] = [h for h in m.get("hooks", []) if "context_uploader" not in h.get("command", "")]
        save_settings(s)


def apply_level(level):
    level = max(0, min(3, level))
    cfg = load_cfg()
    cfg["share_level"]   = level
    cfg["optin_enabled"] = level > 0   # back-compat
    save_cfg(cfg)
    _set_uploader(level > 0)
    return level


# ── Rendering ─────────────────────────────────────────────────────────────────
TRACK_W = 46

def _render(sel):
    t = TIERS[sel]
    lines = []
    lines.append(f"  {B}Earnings sharing{R}")
    lines.append("")
    # top labels: Private … Max payout
    lines.append(f"      {GREY}Private{R}{' ' * (TRACK_W - 17)}{PURPLE}Max payout{R}")
    # track: green up to marker, purple after
    pos = int(sel / (len(TIERS) - 1) * (TRACK_W - 1))
    left  = "━" * pos
    right = "┄" * (TRACK_W - pos - 1)
    lines.append(f"      {GREEN}{left}{R}{WHITE}●{R}{PURPLE}{right}{R}")
    # tier name row, evenly spaced, selected highlighted
    names = []
    for i, tt in enumerate(TIERS):
        nm = tt["name"]
        col = (PINK + B) if (i == sel and tt["key"] == "max") else (WHITE + B) if i == sel else DIM
        names.append(f"{col}{nm}{R}")
    # space them across the track
    slot = TRACK_W // len(TIERS)
    row = "      "
    for i, nm in enumerate(names):
        raw = TIERS[i]["name"]
        pad = max(1, slot - len(raw))
        row += nm + (" " * pad)
    lines.append(row)
    # marker under selected
    marker_col = 6 + int(sel / (len(TIERS) - 1) * (TRACK_W - 1))
    lines.append(" " * marker_col + f"{(PINK if t['key']=='max' else WHITE)}▲{R}")
    lines.append("")
    # multiplier + tag
    mcol = PINK if t["key"] == "max" else GREEN
    uplift = int((t["mult"] - 1) * 100)
    bump = f"{GREEN}+{uplift}% vs private{R}" if uplift > 0 else f"{DIM}base rate{R}"
    lines.append(f"   {mcol}{B}{t['mult']:.1f}× earnings{R}   {DIM}·{R}   {t['tag']}    {bump}")
    for dl in t["desc"].split("\n"):
        lines.append(f"   {GREY}{dl}{R}")
    lines.append("")
    lines.append(f"   {DIM}←/→ to adjust · Enter to confirm · Esc to cancel{R}")
    return lines


def _read_key():
    import termios, tty
    fd = sys.stdin.fileno(); old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            nxt = sys.stdin.read(2)
            if nxt == "[C": return "right"
            if nxt == "[D": return "left"
            return "esc"
        if ch in ("\r", "\n"): return "enter"
        if ch == "\x03": return "esc"
        if ch in ("h", "H"): return "left"
        if ch in ("l", "L"): return "right"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def interactive():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return summary()
    cfg = load_cfg()
    sel = int(cfg.get("share_level", DEFAULT_LEVEL))
    sel = max(0, min(3, sel))

    sys.stdout.write("\033[?25l")  # hide cursor
    lines = _render(sel)
    sys.stdout.write("\n".join(lines) + "\n"); sys.stdout.flush()
    n = len(lines)
    try:
        while True:
            k = _read_key()
            if k == "right" and sel < len(TIERS) - 1: sel += 1
            elif k == "left" and sel > 0: sel -= 1
            elif k == "enter":
                _confirm(sel); break
            elif k == "esc":
                sys.stdout.write(f"\n  {DIM}Cancelled — nothing changed.{R}\n"); break
            else:
                continue
            # re-render in place
            sys.stdout.write(f"\033[{n}A\033[J")
            lines = _render(sel)
            sys.stdout.write("\n".join(lines) + "\n"); sys.stdout.flush()
            n = len(lines)
    finally:
        sys.stdout.write("\033[?25h")  # show cursor
        sys.stdout.flush()


def _confirm(sel):
    level = apply_level(sel)
    t = TIERS[level]
    sys.stdout.write(f"\033[{len(_render(sel))}A\033[J")  # clear the picker
    mcol = PINK if t["key"] == "max" else GREEN
    print()
    if level == 0:
        print(f"  {GREY}Sharing off.{R} You'll earn at the base rate. Run optin.py anytime to earn more.")
    else:
        print(f"  {mcol}{B}{t['tag']} unlocked — {t['mult']:.1f}× earnings.{R}")
        if level == 3:
            print(f"  {PINK}🔥 Max payout. You're in the top tier — the good inventory routes to you.{R}")
        else:
            nxt = TIERS[level + 1]
            print(f"  {DIM}Tip: {nxt['tag']} pays {nxt['mult']:.1f}× — run optin.py again to bump up.{R}")
    print(f"  {DIM}Change anytime: python3 ~/.claude/ads/optin.py{R}")
    print()


def summary():
    cfg = load_cfg(); level = int(cfg.get("share_level", 0))
    print()
    print(f"  {B}Earnings sharing{R}   (current: {TIERS[level]['tag']} · {TIERS[level]['mult']:.1f}×)")
    print()
    for i, t in enumerate(TIERS):
        mark = f"{GREEN}●{R}" if i == level else f"{DIM}○{R}"
        col = PINK if t["key"] == "max" else WHITE
        print(f"   {mark} {col}{t['name']:<9}{R} {t['mult']:.1f}×   {GREY}{t['desc'].splitlines()[0]}{R}")
    print()
    print(f"   Set: python3 ~/.claude/ads/optin.py --level max   (or 0..3 / off)")
    print()


def main():
    args = sys.argv[1:]
    if "--status" in args:
        summary(); return
    if "--disable" in args:
        apply_level(0); print(f"\n  {GREY}Sharing off — base earnings.{R}\n"); return
    if "--enable" in args:
        lvl = apply_level(3); print(f"\n  {PINK}{B}Max payout unlocked — 2.5× earnings.{R}\n"); return
    if "--level" in args:
        try:
            val = args[args.index("--level") + 1].lower()
        except IndexError:
            val = "max"
        mapping = {"off": 0, "private": 0, "stack": 1, "context": 2, "max": 3}
        level = mapping.get(val, int(val) if val.isdigit() else DEFAULT_LEVEL)
        level = apply_level(level)
        print(f"\n  Set to {TIERS[level]['tag']} — {TIERS[level]['mult']:.1f}× earnings.\n"); return
    interactive()


if __name__ == "__main__":
    main()
