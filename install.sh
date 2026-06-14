#!/usr/bin/env bash
# Claude Code Ads — installer
#
# Usage (no referral):
#   curl -fsSL https://raw.githubusercontent.com/bggprogramming/claude-code-ads/main/install.sh | bash
#
# Usage (with referral code):
#   curl -fsSL https://raw.githubusercontent.com/bggprogramming/claude-code-ads/main/install.sh | bash -s -- --ref abc123
#
# What this does:
#   1. Creates ~/.claude/ads/ and installs all scripts
#   2. Installs the certifi Python dependency
#   3. Generates your user ID + referral code, registers you in Supabase
#   4. Patches ~/.claude/settings.json to activate statusLine + hooks
#   5. Shows your referral link

set -euo pipefail

# ── Parse args ────────────────────────────────────────────────────────────────
REF_CODE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF_CODE="${2:-}"; shift 2 ;;
    *)     shift ;;
  esac
done

REPO="https://raw.githubusercontent.com/bggprogramming/claude-code-ads/main"
ADS_DIR="$HOME/.claude/ads"
SETTINGS="$HOME/.claude/settings.json"

echo ""
echo "  Installing Claude Code Ads..."
echo ""

# ── 1. Create ads directory ───────────────────────────────────────────────────
mkdir -p "$ADS_DIR"

# ── 2. Download scripts ───────────────────────────────────────────────────────
FILES=(ad.py update_spinner.py click_server.py start_click_server.sh
       earnings.py setup.py referral.py stats.py ads.json)

for f in "${FILES[@]}"; do
  curl -fsSL "$REPO/$f" -o "$ADS_DIR/$f"
done
chmod +x "$ADS_DIR/start_click_server.sh"

echo "  Scripts installed."

# ── 3. Write default config.json (Supabase credentials) ──────────────────────
# Only write if it doesn't already exist (preserve existing creds + user_id)
if [ ! -f "$ADS_DIR/config.json" ]; then
  cat > "$ADS_DIR/config.json" <<'CONFIGEOF'
{
  "supabase_url": "https://gpbrzpyvzlzwvvymgeyk.supabase.co",
  "supabase_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdwYnJ6cHl2emx6d3Z2eW1nZXlrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE0NjAwNDIsImV4cCI6MjA5NzAzNjA0Mn0.Wh60a8XyYCeKlOJn7HJOMpipTTHmzCRBaH3cEQ0C-vc"
}
CONFIGEOF
fi

# ── 4. Install Python dependency ──────────────────────────────────────────────
echo "  Installing certifi..."
pip3 install --quiet certifi 2>/dev/null || python3 -m pip install --quiet certifi 2>/dev/null || true

# ── 5. Register user + assign referral code ───────────────────────────────────
echo "  Setting up your account..."
if [ -n "$REF_CODE" ]; then
  python3 "$ADS_DIR/setup.py" --ref "$REF_CODE"
else
  python3 "$ADS_DIR/setup.py"
fi

# ── 6. Patch ~/.claude/settings.json ─────────────────────────────────────────
echo "  Activating in Claude Code..."
python3 - <<PYEOF
import json, sys
from pathlib import Path

SETTINGS = Path("$SETTINGS")
ADS      = "$ADS_DIR"

if not SETTINGS.exists():
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    data = {}
else:
    try:
        data = json.loads(SETTINGS.read_text())
    except Exception:
        data = {}

data["statusLine"] = {
    "type":    "command",
    "command": f"python3 {ADS}/ad.py",
}

data.setdefault("hooks", {})
data["hooks"]["SessionStart"] = [{"hooks": [
    {"type": "command", "command": f"bash {ADS}/start_click_server.sh", "async": True},
    {"type": "command", "command": f"python3 {ADS}/update_spinner.py",  "async": True},
]}]
data["hooks"]["Stop"] = [{"hooks": [
    {"type": "command", "command": f"python3 {ADS}/update_spinner.py", "async": True},
]}]

tmp = SETTINGS.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=2))
tmp.replace(SETTINGS)
print("  settings.json updated.")
PYEOF

# ── 7. Done ───────────────────────────────────────────────────────────────────
echo ""
echo "  Done! Restart Claude Code to activate."
echo ""
echo "  Commands:"
echo "    python3 ~/.claude/ads/referral.py   # your referral link + earnings"
echo "    python3 ~/.claude/ads/stats.py      # impression analytics"
echo ""
