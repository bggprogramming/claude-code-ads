#!/usr/bin/env python3
"""
PostToolUse hook — captures tech stack signals from tool invocations.
Runs async after every tool call. Merges signals into the session context
cache so that ad.py and update_spinner.py can use richer context.

Called from: hooks.PostToolUse (async)
Input:  stdin JSON with tool_name, tool_input, session_id, cwd
Output: none (writes to /tmp/claude-ads-ctx-*.json)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import context as _ctx


def main():
    try:
        raw  = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    tool_name   = data.get("tool_name", "")
    tool_input  = data.get("tool_input", {})
    session_id  = data.get("session_id")  # Claude's session UUID
    cwd         = data.get("cwd")

    # If cache is cold, seed it from the filesystem first
    if _ctx.read_cache(session_id) is None and cwd:
        fs_tags = _ctx.detect_from_filesystem(cwd)
        _ctx.write_cache(fs_tags, session_id=session_id)

    # Extract signals from this tool call
    new_tags, new_exts = _ctx.tags_from_tool(tool_name, tool_input)

    if new_tags or new_exts or tool_name:
        _ctx.merge_into_cache(
            new_tags,
            new_tools=[tool_name] if tool_name else [],
            new_exts=list(new_exts),
            session_id=session_id,
        )


if __name__ == "__main__":
    main()
