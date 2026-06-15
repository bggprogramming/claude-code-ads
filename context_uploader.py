#!/usr/bin/env python3
"""
Opt-in Stop hook — uploads session context + last prompt snippet to Supabase.
Only runs when user has explicitly enabled opt-in via: python3 optin.py --enable

Called from: hooks.Stop (async, added only when optin_enabled = true)
Input:  stdin JSON with session_id, transcript_path, cwd
Output: none (uploads to Supabase session_contexts table)

What is collected (per the consent screen in optin.py):
  - user_id (pseudonymous UUID from config.json)
  - session_id (Claude's session UUID)
  - cwd_hash (SHA-256 of project path — one-way, never reversible)
  - tech_stack labels (e.g. ["typescript", "docker"])
  - tools_used list (e.g. ["Bash", "Edit"])
  - file_extensions list (e.g. [".ts", ".yml"])
  - prompt_snippet: first 150 chars of the last user message
"""
import hashlib
import json
import os
import ssl
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import certifi
import context as _ctx

BASE     = Path(__file__).parent
CFG_FILE = BASE / "config.json"
SSL_CTX  = ssl.create_default_context(cafile=certifi.where())


def load_cfg():
    try:
        return json.loads(CFG_FILE.read_text())
    except Exception:
        return {}


def hash_path(path):
    """One-way privacy hash. 16 hex chars — enough to detect repeat visits, impossible to reverse."""
    return hashlib.sha256(path.encode()).hexdigest()[:16]


def read_last_prompt(transcript_path):
    """
    Read the most recent user text message from the session JSONL transcript.
    Returns first 150 chars, or None if unavailable.
    Never returns tool results or file contents — only conversational text.
    """
    try:
        lines = Path(transcript_path).read_text(errors="replace").strip().splitlines()
    except Exception:
        return None

    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "user":
            continue
        msg = obj.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            snippet = content.strip()[:150]
            # Skip if it looks like a tool result (starts with JSON bracket/brace)
            if not snippet.startswith(("[", "{")):
                return snippet
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text and not text.startswith(("[", "{")):
                        return text[:150]
    return None


def main():
    # Parse stdin JSON
    try:
        raw  = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return

    cfg = load_cfg()
    # Earnings-sharing tier (0=private … 3=max). Back-compat: optin_enabled → 1.
    level = int(cfg.get("share_level", 1 if cfg.get("optin_enabled") else 0))
    if level <= 0:
        return  # private — nothing leaves the machine

    session_id      = data.get("session_id", "")
    transcript_path = data.get("transcript_path", "")
    cwd             = data.get("cwd", "")

    # Use the Claude session_id-keyed cache when available
    cached = _ctx.read_cache(session_id)
    if cached:
        tags, tools, exts = cached
    else:
        tags  = _ctx.get_context(cwd=cwd, session_id=session_id)
        tools = []
        exts  = []

    # Tiered payload — only share what the chosen level permits.
    #   1 stack:   tech stack + tools
    #   2 context: + file extensions + hashed cwd
    #   3 max:     + the gist of the last prompt
    payload = {
        "user_id":         cfg.get("user_id", ""),
        "session_id":      session_id,
        "tech_stack":      list(tags),
        "tools_used":      list(tools),
        "file_extensions": list(exts) if level >= 2 else [],
        "cwd_hash":        (hash_path(cwd) if cwd else "") if level >= 2 else "",
        "prompt_snippet":  (read_last_prompt(transcript_path) if transcript_path else None) if level >= 3 else None,
    }

    url = f"{cfg['supabase_url']}/rest/v1/session_contexts"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "apikey":        cfg["supabase_key"],
            "Authorization": f"Bearer {cfg['supabase_key']}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5, context=SSL_CTX)
    except Exception:
        pass


if __name__ == "__main__":
    main()
