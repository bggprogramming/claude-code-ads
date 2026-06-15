#!/bin/bash
# Start click_server.py if not already running.
# Uses an HTTP /health check — more reliable than kill -0 (which passes
# even if the process is zombie or unresponsive).
# Called by SessionStart hook — must be fast and silent.

PID_FILE="$HOME/.claude/ads/click_server.pid"
SCRIPT="$HOME/.claude/ads/click_server.py"
PORT=54323
LOG="$HOME/.claude/ads/click_server.log"

# 1. Try HTTP health check — most reliable signal
if python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('http://127.0.0.1:$PORT/health', timeout=1)
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
    exit 0   # server is live and responding
fi

# 2. Server not responding — kill stale PID file if present
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ]; then
        kill "$OLD_PID" 2>/dev/null
    fi
    rm -f "$PID_FILE"
fi

# 3. Start fresh server — log to file so startup errors are visible
nohup python3 "$SCRIPT" >>"$LOG" 2>&1 &

# 4. Brief wait then verify it came up (non-blocking: exit 0 either way)
sleep 0.5
python3 -c "
import urllib.request, sys
try:
    urllib.request.urlopen('http://127.0.0.1:$PORT/health', timeout=1)
except Exception:
    pass   # first startup may take a moment; hook doesn't need to wait
" 2>/dev/null || true
