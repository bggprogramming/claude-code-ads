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
import time
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


# ── Interactive numbered menu (works in any terminal, through an agent, or piped) ──

def _bar(mult):
    n = int(round(mult / 2.5 * 12))
    return "▓" * n + "░" * (12 - n)


_SHARE_MULT = [1.0, 1.3, 1.7, 2.5]


def _base_per_imp_mc():
    """Estimate the developer's PRIVATE-tier earning per impression (millicents),
    from real history when available, normalized for whatever tier they ran at."""
    try:
        e = json.loads((BASE / "earnings.json").read_text())
    except Exception:
        e = {}
    ti = sum(e.get(k, 0) for k in
             ("imp_statusline", "imp_spinner", "imp_completion", "imp_scrollback", "imp_vscode_statusbar"))
    mc = e.get("total_mc", 0)
    cfg = load_cfg()
    cur = max(0, min(3, int(cfg.get("share_level", 1 if cfg.get("optin_enabled") else 0))))
    per = (mc / ti) if ti > 0 else 2000.0          # mc per impression (~$20 / 1k default)
    return per / _SHARE_MULT[cur]                  # normalize to the private baseline


def _per1k(mult, base=None):
    """Estimated developer earnings, in dollars, per 1,000 ads at this multiplier."""
    base = _base_per_imp_mc() if base is None else base
    return base * mult / 100.0


def _ask(prompt):
    """Read one line, preferring the controlling terminal so this works even when
    stdin is a pipe (e.g. during `curl ... | bash`). Raises EOFError if no TTY."""
    if sys.stdin.isatty():
        return input(prompt)
    try:
        with open("/dev/tty", "r") as tin:
            sys.stdout.write(prompt); sys.stdout.flush()
            line = tin.readline()
            if not line:
                raise EOFError
            return line
    except Exception:
        raise EOFError


def interactive():
    cfg = load_cfg()
    cur = max(0, min(3, int(cfg.get("share_level", 1 if cfg.get("optin_enabled") else 0))))
    base = _base_per_imp_mc()
    base1k = _per1k(1.0, base)
    print()
    print(f"  {B}Earn more by sharing a little context{R}")
    print(f"  {GREY}More context → advertisers can target you → they bid more → you earn more.{R}")
    print()
    for i, t in enumerate(TIERS):
        col   = PINK if t["key"] == "max" else (GREEN if i > 0 else GREY)
        est   = _per1k(t["mult"], base)
        delta = est - base1k
        money = (f"{GREEN}≈ ${est:,.2f}/1k{R}  {GREEN}+${delta:,.2f}{R}"
                 if i > 0 else f"{GREY}≈ ${est:,.2f}/1k  base{R}")
        cur_tag = f"  {GREEN}← current{R}" if i == cur else ""
        star    = f"  {PINK}🔥{R}" if t["key"] == "max" else ""
        print(f"   {B}{i+1}{R}  {col}{t['name']:<8} {t['mult']:.1f}×{R}  {money}{cur_tag}{star}")
        print(f"       {GREY}{t['desc'].splitlines()[0]}{R}")
    print(f"\n  {DIM}≈ per 1,000 ads shown, based on your current pace.{R}")
    print()
    rec = TIERS[DEFAULT_LEVEL]
    try:
        ans = _ask(f"  Type 1-4 and press Enter  "
                   f"{DIM}(Enter = {DEFAULT_LEVEL+1} · {rec['name']}, recommended){R}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {GREY}No change. Run this anytime: python3 ~/.claude/ads/optin.py{R}\n")
        return
    mapping = {"": DEFAULT_LEVEL, "1": 0, "2": 1, "3": 2, "4": 3,
               "private": 0, "off": 0, "stack": 1, "context": 2, "max": 3}
    if ans not in mapping:
        print(f"\n  {GREY}Didn't catch that — no change. Run optin.py again to choose.{R}\n")
        return
    _confirm(mapping[ans])


def _animate(target):
    """Fun level-up: climb private → … → target, bar growing and $ rising."""
    if not sys.stdout.isatty():
        return
    base = _per1k(1.0)
    W = 18
    cols = [GREY, GREEN, GREEN, PINK]
    try:
        for lvl in range(target + 1):
            t = TIERS[lvl]
            amt  = base * t["mult"]
            fill = max(1, int(t["mult"] / 2.5 * W))
            bar  = "▓" * fill + "░" * (W - fill)
            c    = cols[lvl]
            sys.stdout.write(f"\r   {c}[{bar}]{R} {c}{B}{t['name']:<8}{R} {c}{t['mult']:.1f}×{R}  "
                             f"{GREEN}${amt:,.2f}/1k{R}        ")
            sys.stdout.flush()
            time.sleep(0.012 + 0.20)
        if target == 3:
            for s in ("💸", "💸💸", "💸💸💸", "💰 MAX PAYOUT"):
                sys.stdout.write(f"\r   {PINK}[{'▓' * W}]{R} {PINK}{B}max     {R} {PINK}2.5×{R}  "
                                 f"{GREEN}${base * 2.5:,.2f}/1k{R}  {PINK}{s}{R}        ")
                sys.stdout.flush()
                time.sleep(0.16)
        sys.stdout.write("\n")
        sys.stdout.flush()
    except Exception:
        pass


def _confirm(level):
    level = apply_level(level)
    t = TIERS[level]
    mcol = PINK if t["key"] == "max" else GREEN
    print()
    _animate(level)
    if level == 0:
        print(f"  {GREY}Sharing off — base rate.{R} Run optin.py anytime to earn more.")
    else:
        print(f"  {mcol}{B}✓ {t['tag']} — {t['mult']:.1f}× earnings.{R}")
        if level == 3:
            print(f"  {PINK}🔥 Max payout: the good inventory routes to you.{R}")
        else:
            nxt = TIERS[level + 1]
            print(f"  {GREY}Want more? {nxt['name']} pays {nxt['mult']:.1f}× — run optin.py again.{R}")
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
