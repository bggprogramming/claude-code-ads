#!/usr/bin/env bash
# Install the Mango status-bar extension into Cursor / VS Code / Windsurf.
#
# Sideloads by copying the (unpacked) extension into each editor's extensions
# folder — no npm, no vsce, no build step. Reload the editor to activate.
#
#   bash install.sh            # install into every detected editor
#   bash install.sh --uninstall
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ID="adthink.mango-1.0.0"
FILES=(package.json extension.js icon.png)

UNINSTALL=0
[[ "${1:-}" == "--uninstall" ]] && UNINSTALL=1

declare -a EXT_DIRS=()
[[ -d "$HOME/.cursor/extensions"     ]] && EXT_DIRS+=("Cursor:$HOME/.cursor/extensions")
[[ -d "$HOME/.vscode/extensions"     ]] && EXT_DIRS+=("VS Code:$HOME/.vscode/extensions")
[[ -d "$HOME/.windsurf/extensions"   ]] && EXT_DIRS+=("Windsurf:$HOME/.windsurf/extensions")
[[ -d "$HOME/.vscode-oss/extensions" ]] && EXT_DIRS+=("VSCodium:$HOME/.vscode-oss/extensions")

if [[ ${#EXT_DIRS[@]} -eq 0 ]]; then
  echo "  No Cursor / VS Code / Windsurf install found (~/.cursor, ~/.vscode, …)."
  echo "  Open the editor once, then re-run this."
  exit 0
fi

for entry in "${EXT_DIRS[@]}"; do
  name="${entry%%:*}"; dir="${entry#*:}"; target="$dir/$ID"
  if [[ "$UNINSTALL" == "1" ]]; then
    rm -rf "$target" && echo "  ✓ Removed from $name"
    continue
  fi
  mkdir -p "$target"
  for f in "${FILES[@]}"; do cp "$DIR/$f" "$target/$f"; done
  echo "  ✓ Installed into $name"
done

if [[ "$UNINSTALL" != "1" ]]; then
  echo ""
  echo "  Done! Fully quit and reopen the editor to activate."
  echo "  A sponsored line shows bottom-right; click it to visit. Run"
  echo "  \"Mango: Show earnings\" from the command palette to see earnings."
  echo "  Same account as the CLI — you keep 90% of every impression."
fi
