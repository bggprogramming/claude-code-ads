#!/usr/bin/env python3
"""
PreToolUse hook — records when a tool starts so completion_ad.py can
measure elapsed time in PostToolUse and trigger a premium ad if >30s.
"""
import json
import sys
import time
import os
from pathlib import Path

data = {}
try:
    raw = sys.stdin.read(4096)
    if raw.strip():
        data = json.loads(raw)
except Exception:
    pass

session_id = data.get("session_id") or os.environ.get("TERM_SESSION_ID") or "unknown"
safe_sid   = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(session_id))

tool_file = Path(f"/tmp/claude-ads-tool-start-{safe_sid}.json")
try:
    tool_file.write_text(json.dumps({
        "ts":   time.time(),
        "tool": data.get("tool_name", ""),
    }))
except Exception:
    pass
