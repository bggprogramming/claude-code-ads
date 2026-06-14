#!/bin/bash
# Start click_server.py if not already running.
# Called by SessionStart hook — must be fast and silent.
PID_FILE="$HOME/.claude/ads/click_server.pid"
SCRIPT="$HOME/.claude/ads/click_server.py"

if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    exit 0  # already running
  fi
fi

nohup python3 "$SCRIPT" >/dev/null 2>&1 &
