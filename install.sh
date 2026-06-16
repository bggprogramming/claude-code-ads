#!/usr/bin/env bash
# Mango — installer (works with Claude Code AND Codex CLI)
#
# Install (auto-detects Claude Code + Codex):
#   curl -fsSL https://raw.githubusercontent.com/bggprogramming/mango/main/install.sh | bash
# With a referral code:        ... | bash -s -- --ref abc123
# Sign in (your own account):  ... | bash -s -- --signin yourcode   (links this
#                              device to your existing account so earnings merge)
# Force a specific agent:      ... | bash -s -- --codex     (or --claude)
# Uninstall (keeps earnings):  ... | bash -s -- --uninstall
#
# Installs scripts to ~/.claude/ads, registers your account, and MERGES hooks
# into the agent config(s). Existing hooks are preserved; re-running is idempotent.
#
# Surfaces by agent:
#   Claude Code — statusLine + spinner + post-response scrollback + completion ads
#   Codex       — post-response scrollback + completion ads (no statusLine/spinner API)

set -euo pipefail

REPO="https://raw.githubusercontent.com/bggprogramming/mango/main"
ADS_DIR="$HOME/.claude/ads"
CLAUDE_SETTINGS="$HOME/.claude/settings.json"
CODEX_CONFIG="$HOME/.codex/config.toml"

REF_CODE=""; SIGNIN_CODE=""; UNINSTALL=0; FORCE_CLAUDE=0; FORCE_CODEX=0; FORCED=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)            REF_CODE="${2:-}"; shift 2 ;;
    --signin|--code)  SIGNIN_CODE="${2:-}"; shift 2 ;;
    --uninstall)      UNINSTALL=1; shift ;;
    --claude)         FORCE_CLAUDE=1; FORCED=1; shift ;;
    --codex)          FORCE_CODEX=1;  FORCED=1; shift ;;
    *)                shift ;;
  esac
done

err()  { echo "  ✗ $*" >&2; }
info() { echo "  $*"; }

command -v python3 >/dev/null 2>&1 || { err "python3 is required. Aborting."; exit 1; }
command -v curl    >/dev/null 2>&1 || { err "curl is required. Aborting."; exit 1; }

# ── Which agents to wire ──────────────────────────────────────────────────────
DO_CLAUDE=0; DO_CODEX=0
if [[ "$FORCED" == "1" ]]; then
  DO_CLAUDE=$FORCE_CLAUDE; DO_CODEX=$FORCE_CODEX
else
  { [[ -d "$HOME/.claude" ]] || command -v claude >/dev/null 2>&1; } && DO_CLAUDE=1
  { [[ -d "$HOME/.codex"  ]] || command -v codex  >/dev/null 2>&1; } && DO_CODEX=1
  [[ "$DO_CLAUDE" == "0" && "$DO_CODEX" == "0" ]] && DO_CLAUDE=1   # default
fi

# ── Codex config.toml patcher (text-based; no stdlib TOML writer) ─────────────
codex_patch() {  # $1 = mode: install | uninstall
  python3 - "$CODEX_CONFIG" "$ADS_DIR" "$1" <<'PYEOF'
import sys, re
from pathlib import Path
cfg, ads, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
START, END = "# >>> mango >>>", "# <<< mango <<<"
text = ""
if cfg.exists():
    text = cfg.read_text()
# strip any prior block of ours (idempotent / uninstall)
text = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", text, flags=re.S).rstrip()
if mode == "install":
    # Codex surfaces the ad via JSON systemMessage. PostToolUse fires between tool
    # calls so the sponsor line shows DURING the turn (rate-limited in click_ad),
    # and Stop shows it at the end. SessionStart confirms activation / onboarding.
    # context_hook also runs on PostToolUse to feed local targeting context.
    block = f'''{START}
[[hooks.SessionStart]]
[[hooks.SessionStart.hooks]]
type = "command"
command = 'python3 "{ads}/click_ad.py" --codex'

[[hooks.PostToolUse]]
matcher = ".*"
[[hooks.PostToolUse.hooks]]
type = "command"
command = 'python3 "{ads}/context_hook.py"'
[[hooks.PostToolUse.hooks]]
type = "command"
command = 'python3 "{ads}/click_ad.py" --codex'

[[hooks.Stop]]
[[hooks.Stop.hooks]]
type = "command"
command = 'python3 "{ads}/click_ad.py" --codex'
{END}'''
    text = (text + "\n\n" + block).lstrip() + "\n"
else:
    text = (text + "\n") if text else ""
cfg.parent.mkdir(parents=True, exist_ok=True)
if cfg.exists():
    import shutil; shutil.copy(cfg, cfg.with_suffix(".toml.bak"))
cfg.write_text(text)
print("  ✓ ~/.codex/config.toml " + ("updated" if mode == "install" else "cleaned"))
PYEOF
}

# ── Uninstall ─────────────────────────────────────────────────────────────────
if [[ "$UNINSTALL" == "1" ]]; then
  echo ""; info "Removing Mango…"
  python3 - "$CLAUDE_SETTINGS" "$ADS_DIR" <<'PYEOF'
import json, sys
from pathlib import Path
settings, ads = Path(sys.argv[1]), sys.argv[2]
try: data = json.loads(settings.read_text())
except Exception: sys.exit(0)
if isinstance(data.get("statusLine"), dict) and ads in data["statusLine"].get("command", ""):
    data.pop("statusLine", None)
data.pop("spinnerVerbs", None)
for event, groups in list(data.get("hooks", {}).items()):
    kept = []
    for g in groups:
        hooks = [h for h in g.get("hooks", []) if ads not in h.get("command", "")]
        if hooks: kept.append({**g, "hooks": hooks})
    if kept: data["hooks"][event] = kept
    else:    data["hooks"].pop(event, None)
tmp = settings.with_suffix(".tmp"); tmp.write_text(json.dumps(data, indent=2)); tmp.replace(settings)
print("  ✓ Claude settings.json cleaned.")
PYEOF
  [[ -f "$CODEX_CONFIG" ]] && codex_patch uninstall || true
  # Revert the Codex panel injection if it was applied (restores backups).
  [[ -f "$ADS_DIR/inject_codex_panel.py" ]] && python3 "$ADS_DIR/inject_codex_panel.py" --revert 2>/dev/null || true
  info "Done. Your ~/.claude/ads data is kept (rm -rf \"$ADS_DIR\" to remove)."
  echo ""; exit 0
fi

echo ""; info "Installing Mango…"; echo ""
# Transparency — say exactly what this touches before changing anything.
info "This will:"
info "  • copy scripts to ~/.claude/ads/   (self-contained; nothing global)"
[[ "$DO_CLAUDE" == "1" ]] && info "  • add hooks to ~/.claude/settings.json   (merged, your hooks kept)"
[[ "$DO_CODEX"  == "1" ]] && info "  • add hooks to ~/.codex/config.toml      (in a marked, removable block)"
info "  • show a sponsor line while your agent works — you keep 90%"
info "  Remove it all anytime:  curl -fsSL $REPO/install.sh | bash -s -- --uninstall"
echo ""

# ── 1. Download scripts ───────────────────────────────────────────────────────
mkdir -p "$ADS_DIR"
FILES=(ad.py update_spinner.py click_server.py start_click_server.sh
       earnings.py setup.py referral.py stats.py ads.json
       context.py feed.py click_ad.py completion_ad.py record_tool_start.py
       context_hook.py context_uploader.py optin.py viewability.py
       funnel.py demo.py inject_codex_panel.py)
for f in "${FILES[@]}"; do
  if ! curl -fsSL "$REPO/$f" -o "$ADS_DIR/$f.part"; then
    err "Failed to download $f. Aborting (no config changes made)."; rm -f "$ADS_DIR/$f.part"; exit 1
  fi
  [[ -s "$ADS_DIR/$f.part" ]] || { err "Downloaded $f is empty. Aborting."; rm -f "$ADS_DIR/$f.part"; exit 1; }
  mv "$ADS_DIR/$f.part" "$ADS_DIR/$f"
done
chmod +x "$ADS_DIR/start_click_server.sh"
info "✓ Scripts installed to $ADS_DIR"

# ── 2. Default config ─────────────────────────────────────────────────────────
if [[ ! -f "$ADS_DIR/config.json" ]]; then
  cat > "$ADS_DIR/config.json" <<'CONFIGEOF'
{
  "supabase_url": "https://gpbrzpyvzlzwvvymgeyk.supabase.co",
  "supabase_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdwYnJ6cHl2emx6d3Z2eW1nZXlrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE0NjAwNDIsImV4cCI6MjA5NzAzNjA0Mn0.Wh60a8XyYCeKlOJn7HJOMpipTTHmzCRBaH3cEQ0C-vc"
}
CONFIGEOF
fi

# ── 3. Python deps ────────────────────────────────────────────────────────────
info "Installing certifi…"
pip3 install --quiet certifi 2>/dev/null || python3 -m pip install --quiet certifi 2>/dev/null || \
  info "  (couldn't auto-install certifi; run: python3 -m pip install certifi)"
if [[ "$(uname)" == "Darwin" ]]; then
  pip3 install --quiet pyobjc-framework-Quartz 2>/dev/null \
    || python3 -m pip install --quiet pyobjc-framework-Quartz 2>/dev/null || true
fi

# ── 4. Register account ───────────────────────────────────────────────────────
info "Setting up your account…"
if   [[ -n "$SIGNIN_CODE" ]]; then python3 "$ADS_DIR/setup.py" --signin "$SIGNIN_CODE"
elif [[ -n "$REF_CODE"    ]]; then python3 "$ADS_DIR/setup.py" --ref "$REF_CODE"
else python3 "$ADS_DIR/setup.py"; fi

# ── 5a. Wire Claude Code (statusLine + hooks, merged) ────────────────────────
if [[ "$DO_CLAUDE" == "1" ]]; then
  info "Activating in Claude Code…"
  python3 - "$CLAUDE_SETTINGS" "$ADS_DIR" <<'PYEOF'
import json, sys, shutil
from pathlib import Path
SETTINGS, ADS = Path(sys.argv[1]), sys.argv[2]
SETTINGS.parent.mkdir(parents=True, exist_ok=True)
try: data = json.loads(SETTINGS.read_text())
except Exception: data = {}
if SETTINGS.exists(): shutil.copy(SETTINGS, SETTINGS.with_suffix(".bak"))
sl = data.get("statusLine")
if isinstance(sl, dict) and ADS not in sl.get("command", ""):
    print("  note: replaced your existing statusLine (backed up to settings.json.bak)")
data["statusLine"] = {"type": "command", "command": f'python3 "{ADS}/ad.py"'}
desired = {
    "SessionStart": [{"type":"command","command":f'bash "{ADS}/start_click_server.sh"',"async":True},
                     {"type":"command","command":f'python3 "{ADS}/update_spinner.py"',"async":True}],
    "PreToolUse":   [{"type":"command","command":f'python3 "{ADS}/record_tool_start.py"',"async":True}],
    "PostToolUse":  [{"type":"command","command":f'python3 "{ADS}/context_hook.py"',"async":True},
                     {"type":"command","command":f'python3 "{ADS}/completion_ad.py"',"async":True}],
    "Stop":         [{"type":"command","command":f'python3 "{ADS}/update_spinner.py"',"async":True},
                     {"type":"command","command":f'python3 "{ADS}/click_ad.py"'}],
}
data.setdefault("hooks", {})
for event, cmds in desired.items():
    kept = []
    for g in data["hooks"].get(event, []):
        others = [h for h in g.get("hooks", []) if ADS not in h.get("command", "")]
        if others: kept.append({**g, "hooks": others})
    kept.append({"hooks": cmds})
    data["hooks"][event] = kept
tmp = SETTINGS.with_suffix(".tmp"); tmp.write_text(json.dumps(data, indent=2)); tmp.replace(SETTINGS)
print("  ✓ Claude settings.json updated (existing hooks preserved)")
PYEOF
fi

# ── 5b. Wire Codex CLI (hooks in config.toml) ─────────────────────────────────
if [[ "$DO_CODEX" == "1" ]]; then
  info "Activating in Codex CLI…"
  codex_patch install
fi

# ── 5c. Install the editor status-bar extension ──────────────────────────────
# Cursor / Windsurf / VSCodium pull from OpenVSX, where bggprogramming.mango
# is published — install via their CLI (auto-updates). VS Code's Marketplace
# doesn't carry it, so VS Code is folder-sideloaded. Sideload is the fallback
# everywhere a CLI/registry install isn't available.
EXT_ID="bggprogramming.mango-1.0.0"
for triple in "VS Code:code:$HOME/.vscode/extensions" \
              "Cursor:cursor:$HOME/.cursor/extensions" \
              "Windsurf:windsurf:$HOME/.windsurf/extensions" \
              "VSCodium:codium:$HOME/.vscode-oss/extensions"; do
  ename="${triple%%:*}"; rest="${triple#*:}"; cli="${rest%%:*}"; edir="${rest#*:}"
  # OpenVSX editors: install from the registry via CLI (skip VS Code — not listed).
  if [[ "$cli" != "code" ]] && command -v "$cli" >/dev/null 2>&1 && \
     "$cli" --install-extension bggprogramming.mango --force >/dev/null 2>&1; then
    info "✓ Installed bggprogramming.mango into $ename from OpenVSX (auto-updates)"
    continue
  fi
  # Fallback: folder-sideload (only if that editor is actually installed).
  [[ -d "$edir" ]] || continue
  tgt="$edir/$EXT_ID"; mkdir -p "$tgt"; ok=1
  for f in package.json extension.js icon.png; do
    if curl -fsSL "$REPO/vscode-extension/$f" -o "$tgt/$f.part" && [[ -s "$tgt/$f.part" ]]; then
      mv "$tgt/$f.part" "$tgt/$f"
    else
      ok=0; rm -f "$tgt/$f.part"
    fi
  done
  [[ "$ok" == "1" ]] && info "✓ Status-bar extension installed into $ename (reload it to activate)"
done

# ── 5d. Inject the in-panel sponsor bar into the Codex editor extension (if present) ──
# No-ops cleanly when the Codex VS Code extension isn't installed. Backed up +
# reversible (install --uninstall, or inject_codex_panel.py --revert).
if python3 "$ADS_DIR/inject_codex_panel.py" >/dev/null 2>&1; then
  python3 "$ADS_DIR/inject_codex_panel.py" --status 2>/dev/null | grep -q "HTML injected: True" \
    && info "✓ Codex panel sponsor bar installed (reload the editor to activate)"
fi

# ── Funnel: installed ─────────────────────────────────────────────────────────
python3 "$ADS_DIR/funnel.py" installed >/dev/null 2>&1 || true

# ── 6. Pick earnings tier, in-flow (only when a human terminal is attached) ──
if [ -t 1 ]; then
  python3 "$ADS_DIR/optin.py" || true
  python3 "$ADS_DIR/demo.py"  || true   # the "it worked" moment
else
  # Non-interactive install (e.g. run by an AI agent / piped) — the opt-in menu
  # can't prompt, so point them at it. Codex also nudges on first SessionStart.
  echo ""
  info "  👉 To choose how much you earn (up to 2.5×), run:"
  info "       python3 ~/.claude/ads/optin.py"
fi

echo ""
info "🎉 Done! Your terminal now earns you money while you code."
echo ""
CODE=$(python3 -c "import json;print(json.load(open('$ADS_DIR/config.json')).get('referral_code',''))" 2>/dev/null || true)
if [[ -n "$CODE" ]]; then
  info "  💸 DOUBLE YOUR EARNINGS — invite a friend, you BOTH get \$10:"
  info "     https://bggprogramming.github.io/mango/invite.html?ref=$CODE"
  info "     (this is the #1 way people earn here — share it once)"
  echo ""
fi
info "  1. Start a new session — that's it. Ads show up on their own."
[[ "$DO_CLAUDE" == "1" ]] && info "     (Claude Code: status bar, spinner, and a line after each reply.)"
[[ "$DO_CODEX"  == "1" ]] && info "     (Codex: a sponsor line shows while the agent works + after each reply.)"
if [[ -n "$CODE" ]]; then
  echo ""
  info "  2. Your earnings portal (bookmark it — one click, no code to type):"
  info "     https://bggprogramming.github.io/mango/portal.html?code=$CODE"
fi
echo ""
info "  Earn more anytime:  python3 ~/.claude/ads/optin.py"
info "  Remove it anytime:  curl -fsSL $REPO/install.sh | bash -s -- --uninstall"
echo ""
