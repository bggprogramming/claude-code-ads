#!/usr/bin/env python3
"""
Opt-in / opt-out for prompt & context data collection.

  Enable:   python3 ~/.claude/ads/optin.py --enable
  Disable:  python3 ~/.claude/ads/optin.py --disable
  Status:   python3 ~/.claude/ads/optin.py

When enabled, a Stop hook uploads anonymized context signals (tech stack,
tools used, and the first 150 chars of your last message) to Supabase
after each Claude response. This data is used to serve more relevant ads,
which pays you more per impression.
"""
import json
import sys
from pathlib import Path

BASE      = Path(__file__).parent
CFG_FILE  = BASE / "config.json"
SETTINGS  = Path.home() / ".claude" / "settings.json"
UPLOADER  = str(BASE / "context_uploader.py")

CONSENT = """
  ┌──────────────────────────────────────────────────────────────┐
  │               Optional: smarter ad targeting                 │
  │                                                              │
  │  With your permission, after each response we collect:       │
  │                                                              │
  │  ✓  Tech stack labels detected from your project files       │
  │     (e.g. "TypeScript", "Docker")                            │
  │  ✓  Tool names used in this turn (Bash, Edit, Read…)         │
  │  ✓  File extensions edited (.ts, .py, .rs…)                  │
  │  ✓  First 150 chars of your last prompt                      │
  │  ✓  Session timestamp                                        │
  │                                                              │
  │  We NEVER collect:                                           │
  │  ✗  File contents or full file paths                         │
  │  ✗  Claude's responses                                       │
  │  ✗  Secrets, API keys, or environment variables              │
  │  ✗  Your project path (it is one-way hashed before upload)   │
  │                                                              │
  │  This data improves targeting → more relevant ads →          │
  │  higher CPMs → more money for you.                           │
  │                                                              │
  │  You can opt out at any time:                                │
  │    python3 ~/.claude/ads/optin.py --disable                  │
  └──────────────────────────────────────────────────────────────┘
"""

UPLOADER_HOOK = {
    "type":    "command",
    "command": f"python3 {UPLOADER}",
    "async":   True,
}


def load_cfg():
    try:
        return json.loads(CFG_FILE.read_text())
    except Exception:
        return {}


def save_cfg(cfg):
    CFG_FILE.write_text(json.dumps(cfg, indent=2))


def load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except Exception:
        return {}


def save_settings(s):
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2))
    tmp.replace(SETTINGS)


def _uploader_present(settings):
    for matcher in settings.get("hooks", {}).get("Stop", []):
        for hook in matcher.get("hooks", []):
            if "context_uploader" in hook.get("command", ""):
                return True
    return False


def enable():
    cfg = load_cfg()
    cfg["optin_enabled"] = True
    save_cfg(cfg)

    # Inject the uploader into the Stop hooks if not already there
    s = load_settings()
    if not _uploader_present(s):
        stop_hooks = s.setdefault("hooks", {}).setdefault("Stop", [])
        if stop_hooks:
            stop_hooks[0].setdefault("hooks", []).append(UPLOADER_HOOK)
        else:
            stop_hooks.append({"hooks": [UPLOADER_HOOK]})
        save_settings(s)

    print()
    print("  Opt-in enabled. Context data will be uploaded after each response.")
    print("  Disable any time: python3 ~/.claude/ads/optin.py --disable")
    print()


def disable():
    cfg = load_cfg()
    cfg["optin_enabled"] = False
    save_cfg(cfg)

    # Remove the uploader hook from settings.json
    s = load_settings()
    changed = False
    for matcher in s.get("hooks", {}).get("Stop", []):
        hooks = matcher.get("hooks", [])
        before = len(hooks)
        matcher["hooks"] = [h for h in hooks if "context_uploader" not in h.get("command", "")]
        if len(matcher["hooks"]) < before:
            changed = True
    if changed:
        save_settings(s)

    print()
    print("  Opt-in disabled. No context data will be collected.")
    print()


def status():
    cfg = load_cfg()
    s   = load_settings()
    enabled = cfg.get("optin_enabled", False)
    in_hooks = _uploader_present(s)
    print()
    print(f"  Context opt-in: {'ENABLED' if enabled else 'DISABLED'}")
    print(f"  Stop hook installed: {'yes' if in_hooks else 'no'}")
    if not enabled:
        print()
        print("  To enable: python3 ~/.claude/ads/optin.py --enable")
    print()


def interactive():
    print(CONSENT)
    try:
        answer = input("  Enable context data collection? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Cancelled.")
        return
    if answer in ("y", "yes"):
        enable()
    else:
        print()
        print("  Skipped. Run again with --enable to opt in at any time.")
        print()


def main():
    args = sys.argv[1:]
    if "--enable" in args:
        enable()
    elif "--disable" in args:
        disable()
    elif "--status" in args:
        status()
    else:
        interactive()


if __name__ == "__main__":
    main()
