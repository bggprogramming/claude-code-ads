#!/bin/bash
# Install the Claude Code Ads VS Code extension.
# Works with VS Code, Cursor, Windsurf, and any VS Code fork.
# Requires Node.js + npm.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VSIX="$DIR/claude-code-ads.vsix"

echo "Building claude-code-ads VS Code extension..."

# Install vsce if not present
if ! command -v vsce &>/dev/null; then
  echo "Installing @vscode/vsce..."
  npm install -g @vscode/vsce
fi

# Package (suppress license warning for private use)
cd "$DIR"
vsce package --allow-missing-repository --no-git-tag-version 2>/dev/null || \
  vsce package --allow-missing-repository 2>/dev/null || \
  vsce package

# Find the built VSIX
VSIX_BUILT="$(ls "$DIR"/*.vsix 2>/dev/null | head -1)"
if [ -z "$VSIX_BUILT" ]; then
  echo "ERROR: VSIX not built. Check for errors above."
  exit 1
fi

echo "Installing extension..."
# Try all common VS Code forks
INSTALLED=0
for cmd in code cursor windsurf codium; do
  if command -v "$cmd" &>/dev/null; then
    "$cmd" --install-extension "$VSIX_BUILT" && INSTALLED=1 && echo "Installed into: $cmd"
  fi
done

if [ "$INSTALLED" -eq 0 ]; then
  echo "No VS Code editor found in PATH."
  echo "Install manually: open VS Code → Extensions → '...' → 'Install from VSIX' → $VSIX_BUILT"
fi

echo ""
echo "Done! Reload VS Code to activate. Ads will appear in the bottom-right status bar."
echo "You earn \$0.025 per session (same 90% rev share as Claude Code CLI)."
