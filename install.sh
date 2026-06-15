#!/usr/bin/env bash
# Claude Code Ads — installer
#
# Install:
#   curl -fsSL https://raw.githubusercontent.com/bggprogramming/claude-code-ads/main/install.sh | bash
# Install with a referral code:
#   curl -fsSL .../install.sh | bash -s -- --ref abc123
# Uninstall (removes hooks/statusLine; keeps your earnings data):
#   curl -fsSL .../install.sh | bash -s -- --uninstall
#
# What it does: installs scripts to ~/.claude/ads, registers your account,
# and MERGES the statusLine + hooks into ~/.claude/settings.json (existing
# hooks are preserved; re-running is safe/idempotent).

set -euo pipefail

REPO="https://raw.githubusercontent.com/bggprogramming/claude-code-ads/main"
ADS_DIR="$HOME/.claude/ads"
SETTINGS="$HOME/.claude/settings.json"

REF_CODE=""
UNINSTALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)       REF_CODE="${2:-}"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    *)           shift ;;
  esac
done

err() { echo "  ✗ $*" >&2; }
info() { echo "  $*"; }

# ── Prerequisites ─────────────────────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { err "python3 is required (https://python.org). Aborting."; exit 1; }
command -v curl    >/dev/null 2>&1 || { err "curl is required. Aborting."; exit 1; }

# ── Uninstall path ──────────────────────────────────────────────────────────
if [[ "$UNINSTALL" == "1" ]]; then
  echo ""
  info "Removing Claude Code Ads from settings.json…"
  python3 - "$SETTINGS" "$ADS_DIR" <<'PYEOF'
import json, sys
from pathlib import Path
settings, ads = Path(sys.argv[1]), sys.argv[2]
try:
    data = json.loads(settings.read_text())
except Exception:
    sys.exit(0)
# Drop our statusLine + spinnerVerbs
if isinstance(data.get("statusLine"), dict) and ads in data["statusLine"].get("command", ""):
    data.pop("statusLine", None)
data.pop("spinnerVerbs", None)
# Strip our hook entries, keep everyone else's
for event, groups in list(data.get("hooks", {}).items()):
    kept = []
    for g in groups:
        hooks = [h for h in g.get("hooks", []) if ads not in h.get("command", "")]
        if hooks: kept.append({**g, "hooks": hooks})
    if kept: data["hooks"][event] = kept
    else:    data["hooks"].pop(event, None)
tmp = settings.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2)); tmp.replace(settings)
print("  settings.json cleaned.")
PYEOF
  info "Done. Your ~/.claude/ads data is kept — delete it manually if you want: rm -rf \"$ADS_DIR\""
  echo ""
  exit 0
fi

echo ""
info "Installing Claude Code Ads…"
echo ""

# ── 1. Download scripts ───────────────────────────────────────────────────────
mkdir -p "$ADS_DIR"
FILES=(ad.py update_spinner.py click_server.py start_click_server.sh
       earnings.py setup.py referral.py stats.py ads.json
       context.py feed.py click_ad.py completion_ad.py record_tool_start.py
       context_hook.py context_uploader.py optin.py viewability.py)

for f in "${FILES[@]}"; do
  if ! curl -fsSL "$REPO/$f" -o "$ADS_DIR/$f.part"; then
    err "Failed to download $f. Aborting (no changes made to settings)."; rm -f "$ADS_DIR/$f.part"; exit 1
  fi
  [[ -s "$ADS_DIR/$f.part" ]] || { err "Downloaded $f is empty. Aborting."; rm -f "$ADS_DIR/$f.part"; exit 1; }
  mv "$ADS_DIR/$f.part" "$ADS_DIR/$f"
done
chmod +x "$ADS_DIR/start_click_server.sh"
info "✓ Scripts installed to $ADS_DIR"

# ── 2. Default config (preserve existing creds/user_id) ──────────────────────
if [[ ! -f "$ADS_DIR/config.json" ]]; then
  cat > "$ADS_DIR/config.json" <<'CONFIGEOF'
{
  "supabase_url": "https://gpbrzpyvzlzwvvymgeyk.supabase.co",
  "supabase_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdwYnJ6cHl2emx6d3Z2eW1nZXlrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE0NjAwNDIsImV4cCI6MjA5NzAzNjA0Mn0.Wh60a8XyYCeKlOJn7HJOMpipTTHmzCRBaH3cEQ0C-vc"
}
CONFIGEOF
fi

# ── 3. Python dependency ──────────────────────────────────────────────────────
info "Installing certifi…"
pip3 install --quiet certifi 2>/dev/null || python3 -m pip install --quiet certifi 2>/dev/null || \
  info "  (couldn't auto-install certifi; run: python3 -m pip install certifi)"

# Optional (macOS): window-viewability so impressions only count when the
# terminal is actually visible. Degrades gracefully if this can't install.
if [[ "$(uname)" == "Darwin" ]]; then
  pip3 install --quiet pyobjc-framework-Quartz 2>/dev/null \
    || python3 -m pip install --quiet pyobjc-framework-Quartz 2>/dev/null || true
fi

# ── 4. Register account ───────────────────────────────────────────────────────
info "Setting up your account…"
if [[ -n "$REF_CODE" ]]; then python3 "$ADS_DIR/setup.py" --ref "$REF_CODE"; else python3 "$ADS_DIR/setup.py"; fi

# ── 5. Merge statusLine + hooks into settings.json (preserve existing) ───────
info "Activating in Claude Code…"
python3 - "$SETTINGS" "$ADS_DIR" <<'PYEOF'
import json, sys, shutil
from pathlib import Path

SETTINGS, ADS = Path(sys.argv[1]), sys.argv[2]
SETTINGS.parent.mkdir(parents=True, exist_ok=True)
try:
    data = json.loads(SETTINGS.read_text())
except Exception:
    data = {}

# Back up once before touching anything.
if SETTINGS.exists():
    shutil.copy(SETTINGS, SETTINGS.with_suffix(".bak"))

# statusLine — note if we're replacing a different one.
existing_sl = data.get("statusLine")
if isinstance(existing_sl, dict) and ADS not in existing_sl.get("command", ""):
    print(f"  note: replaced your existing statusLine (backed up to settings.json.bak)")
data["statusLine"] = {"type": "command", "command": f'python3 "{ADS}/ad.py"'}

# Hooks — desired commands per event.
desired = {
    "SessionStart": [
        {"type": "command", "command": f'bash "{ADS}/start_click_server.sh"', "async": True},
        {"type": "command", "command": f'python3 "{ADS}/update_spinner.py"',  "async": True},
    ],
    "PreToolUse": [
        {"type": "command", "command": f'python3 "{ADS}/record_tool_start.py"', "async": True},
    ],
    "PostToolUse": [
        {"type": "command", "command": f'python3 "{ADS}/context_hook.py"',  "async": True},
        {"type": "command", "command": f'python3 "{ADS}/completion_ad.py"', "async": True},
    ],
    "Stop": [
        {"type": "command", "command": f'python3 "{ADS}/update_spinner.py"', "async": True},
        {"type": "command", "command": f'python3 "{ADS}/click_ad.py"'},
    ],
}

data.setdefault("hooks", {})
for event, cmds in desired.items():
    groups = data["hooks"].get(event, [])
    # Drop any prior entries of ours (idempotent re-install), keep the user's.
    kept = []
    for g in groups:
        others = [h for h in g.get("hooks", []) if ADS not in h.get("command", "")]
        if others: kept.append({**g, "hooks": others})
    kept.append({"hooks": cmds})
    data["hooks"][event] = kept

tmp = SETTINGS.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2)); tmp.replace(SETTINGS)
print("  ✓ settings.json updated (existing hooks preserved)")
PYEOF

echo ""
info "Done! Restart Claude Code to activate."
echo ""
info "Commands:"
info "  python3 ~/.claude/ads/referral.py   # your referral link + earnings"
info "  python3 ~/.claude/ads/stats.py      # impression analytics"
echo ""
info "Works in any terminal that runs Claude Code (Terminal, iTerm2, VS Code/Cursor)."
info "Uninstall anytime:  curl -fsSL $REPO/install.sh | bash -s -- --uninstall"
echo ""
