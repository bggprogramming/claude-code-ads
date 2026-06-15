#!/usr/bin/env python3
"""
End-to-end test for contextual targeting + opt-in prompt storage.

Tests:
  1. Filesystem context detection (simulated Python, TypeScript, Rust projects)
  2. Tool-derived context signals (file extension + bash command extraction)
  3. Session context cache (read/write/merge/TTL)
  4. Context-boosted ad selection (relevant ad gets higher selection rate)
  5. PostToolUse hook (stdin JSON → cache update, end-to-end)
  6. Opt-in enable/disable (config.json + settings.json mutation)
  7. context_uploader.py (simulated transcript → Supabase upload)
  8. Supabase session_contexts table (query by user_id)

Run: python3 ~/.claude/ads/test_contextual.py
"""
import json
import os
import random
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import certifi
import context as _ctx

BASE     = Path(__file__).parent
CFG_FILE = BASE / "config.json"
SSL_CTX  = ssl.create_default_context(cafile=certifi.where())
SEP      = "  " + "─" * 54


def load_cfg():
    with open(CFG_FILE) as f:
        return json.load(f)


def api(cfg, method, path, payload=None, params=""):
    url = f"{cfg['supabase_url']}/rest/v1/{path}{params}"
    headers = {
        "apikey":        cfg["supabase_key"],
        "Authorization": f"Bearer {cfg['supabase_key']}",
        "Content-Type":  "application/json",
    }
    if payload is not None:
        headers["Prefer"] = "return=minimal"
    data = json.dumps(payload).encode() if payload else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=8, context=SSL_CTX)
    body = resp.read()
    return json.loads(body) if body else None


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  →  {detail}" if detail else ""))
    return condition


def main():
    cfg     = load_cfg()
    results = []
    test_sid = f"test-ctx-{int(time.time())}"  # unique per run

    print()
    print("  Contextual targeting + opt-in prompt storage — E2E test")
    print(SEP)

    # ── 1. Filesystem context detection ───────────────────────────────────────
    print()
    print("  1 — Filesystem context detection")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)

        # Python project
        (td / "requirements.txt").write_text("flask==3.0.0\n")
        (td / "pyproject.toml").write_text("[project]\nname='app'\n")
        tags = _ctx.detect_from_filesystem(str(td))
        results.append(check("Python project detected",
                             "python" in tags, f"tags={sorted(tags)}"))

        # TypeScript project
        (td / "requirements.txt").unlink()
        (td / "pyproject.toml").unlink()
        (td / "package.json").write_text(json.dumps({
            "devDependencies": {"typescript": "^5.0.0", "@types/node": "^20"}
        }))
        (td / "tsconfig.json").write_text("{}")
        tags = _ctx.detect_from_filesystem(str(td))
        results.append(check("TypeScript project detected",
                             "typescript" in tags and "javascript" in tags,
                             f"tags={sorted(tags)}"))

        # Rust project
        (td / "package.json").unlink()
        (td / "tsconfig.json").unlink()
        (td / "Cargo.toml").write_text("[package]\nname='myapp'\n")
        tags = _ctx.detect_from_filesystem(str(td))
        results.append(check("Rust project detected",
                             "rust" in tags, f"tags={sorted(tags)}"))

        # Docker project
        (td / "Dockerfile").write_text("FROM python:3.12\n")
        (td / "docker-compose.yml").write_text("services:\n  app:\n    build: .\n")
        tags = _ctx.detect_from_filesystem(str(td))
        results.append(check("Docker signals detected",
                             "docker" in tags, f"tags={sorted(tags)}"))

    print()
    print(SEP)

    # ── 2. Tool-derived signals ────────────────────────────────────────────────
    print()
    print("  2 — Tool-derived context signals")
    print()

    cases = [
        ("Edit", {"file_path": "/app/src/index.ts"},   {"typescript", "javascript"}, {".ts"}),
        ("Edit", {"file_path": "/app/main.py"},         {"python"},                   {".py"}),
        ("Edit", {"file_path": "/app/Dockerfile"},      {"docker"},                   set()),
        ("Bash", {"command":   "cargo build --release"}, {"rust"},                    set()),
        ("Bash", {"command":   "npm run dev"},           {"javascript"},              set()),
        ("Bash", {"command":   "python3 manage.py runserver"}, {"python"},           set()),
        ("Bash", {"command":   "kubectl apply -f k8s/"}, {"infra"},                  set()),
        ("Read", {"file_path": "/app/go.sum"},           set(),                      set()),  # .sum has no ext tag
    ]

    for tool, inp, exp_tags, exp_exts in cases:
        got_tags, got_exts = _ctx.tags_from_tool(tool, inp)
        ok = exp_tags <= got_tags  # expected is a subset
        results.append(check(
            f"  {tool}({list(inp.values())[0][:35]}) → {sorted(exp_tags) or '∅'}",
            ok,
            f"got tags={sorted(got_tags)}"
        ))

    print()
    print(SEP)

    # ── 3. Session context cache ───────────────────────────────────────────────
    print()
    print("  3 — Session context cache (read/write/merge/TTL)")
    print()

    _ctx.write_cache({"python", "docker"}, ["Bash", "Edit"], [".py"], test_sid)
    cached = _ctx.read_cache(test_sid)
    results.append(check("Cache write → read round-trip",
                         cached is not None and "python" in cached[0],
                         str(cached[0] if cached else "None")))

    _ctx.merge_into_cache({"rust"}, ["Read"], [".rs"], test_sid)
    merged = _ctx.read_cache(test_sid)
    results.append(check("Merge adds new tags without losing existing",
                         merged and {"python", "docker", "rust"} <= merged[0],
                         str(sorted(merged[0]) if merged else "None")))

    results.append(check("Merge appends new tools",
                         merged and "Read" in merged[1] and "Bash" in merged[1],
                         str(merged[1] if merged else "None")))

    # Verify expired cache returns None
    _ctx.write_cache({"python"}, session_id=test_sid + "_stale")
    stale_path = _ctx._cache_path(test_sid + "_stale")
    data = json.loads(stale_path.read_text())
    data["ts"] = time.time() - 7200  # 2 hours ago
    stale_path.write_text(json.dumps(data))
    expired = _ctx.read_cache(test_sid + "_stale")
    results.append(check("Expired cache (>TTL) returns None",
                         expired is None, "correctly expired"))

    print()
    print(SEP)

    # ── 4. Context-boosted ad selection ───────────────────────────────────────
    print()
    print("  4 — Context-boosted ad selection (statistical)")
    print()

    # Simulate ads.json structure
    fake_ads = [
        {"id": "ad_python",  "text": "PyTools ad",  "weight": 33, "cpm": 25, "tags": ["python"]},
        {"id": "ad_generic", "text": "Generic ad",  "weight": 33, "cpm": 22, "tags": []},
        {"id": "ad_rust",    "text": "Rust ad",     "weight": 34, "cpm": 20, "tags": ["rust"]},
    ]
    python_context = {"python"}
    n_trials = 1000

    counts = {"ad_python": 0, "ad_generic": 0, "ad_rust": 0}
    for _ in range(n_trials):
        ad = _ctx.weighted_sample(fake_ads, python_context)
        counts[ad["id"]] += 1

    python_pct  = counts["ad_python"]  / n_trials * 100
    generic_pct = counts["ad_generic"] / n_trials * 100
    rust_pct    = counts["ad_rust"]    / n_trials * 100

    print(f"  Python context — {n_trials} trials:")
    print(f"    ad_python  (tags=['python']): {python_pct:.1f}%  (expected ~{33*2.5/(33*2.5+33+34)*100:.0f}%)")
    print(f"    ad_generic (tags=[]):         {generic_pct:.1f}%")
    print(f"    ad_rust    (tags=['rust']):   {rust_pct:.1f}%")

    results.append(check("Python ad wins majority with python context",
                         python_pct > 50,
                         f"{python_pct:.1f}% > 50%"))
    results.append(check("Rust ad still gets some rotation",
                         rust_pct > 5,
                         f"{rust_pct:.1f}% > 5%"))
    results.append(check("Boost ratio python/rust ≈ 2.5×",
                         abs(python_pct / rust_pct - 2.5) < 1.2,
                         f"{python_pct/rust_pct:.2f}× (target {_ctx.BOOST}×)"))

    print()
    print(SEP)

    # ── 5. PostToolUse hook stdin processing ──────────────────────────────────
    print()
    print("  5 — PostToolUse hook (stdin JSON → context cache)")
    print()

    hook_sid = test_sid + "_hook"
    stdin_payload = json.dumps({
        "session_id": hook_sid,
        "cwd":        "/dev/null",  # no real project
        "tool_name":  "Edit",
        "tool_input": {"file_path": "/project/src/lib.rs", "old_string": "a", "new_string": "b"},
    })

    proc = subprocess.run(
        [sys.executable, str(BASE / "context_hook.py")],
        input=stdin_payload, capture_output=True, text=True, timeout=5,
    )
    results.append(check("context_hook.py exits cleanly",
                         proc.returncode == 0,
                         proc.stderr[:80] if proc.stderr else "ok"))

    hook_cache = _ctx.read_cache(hook_sid)
    results.append(check("Hook wrote rust tag to cache",
                         hook_cache is not None and "rust" in hook_cache[0],
                         str(hook_cache[0] if hook_cache else "None")))
    results.append(check("Hook recorded Edit in tools",
                         hook_cache is not None and "Edit" in hook_cache[1],
                         str(hook_cache[1] if hook_cache else "None")))
    results.append(check("Hook recorded .rs extension",
                         hook_cache is not None and ".rs" in hook_cache[2],
                         str(hook_cache[2] if hook_cache else "None")))

    print()
    print(SEP)

    # ── 6. Opt-in enable / disable ────────────────────────────────────────────
    print()
    print("  6 — Opt-in enable/disable (config.json + settings.json)")
    print()

    SETTINGS = Path.home() / ".claude" / "settings.json"
    orig_settings = SETTINGS.read_text()
    orig_cfg      = (BASE / "config.json").read_text()

    # Enable
    r = subprocess.run([sys.executable, str(BASE / "optin.py"), "--enable"],
                       capture_output=True, text=True, timeout=5)
    results.append(check("optin.py --enable exits 0",
                         r.returncode == 0, r.stderr[:60] if r.stderr else "ok"))

    cfg_after = json.loads((BASE / "config.json").read_text())
    results.append(check("optin_enabled = true in config.json",
                         cfg_after.get("optin_enabled") is True,
                         str(cfg_after.get("optin_enabled"))))

    s_after = json.loads(SETTINGS.read_text())
    present = any(
        "context_uploader" in h.get("command", "")
        for matcher in s_after.get("hooks", {}).get("Stop", [])
        for h in matcher.get("hooks", [])
    )
    results.append(check("context_uploader hook added to settings.json",
                         present, "found in Stop hooks"))

    # Disable
    r2 = subprocess.run([sys.executable, str(BASE / "optin.py"), "--disable"],
                        capture_output=True, text=True, timeout=5)
    s_after2 = json.loads(SETTINGS.read_text())
    gone = not any(
        "context_uploader" in h.get("command", "")
        for matcher in s_after2.get("hooks", {}).get("Stop", [])
        for h in matcher.get("hooks", [])
    )
    results.append(check("optin.py --disable removes hook from settings.json",
                         gone, "context_uploader removed"))

    cfg_after2 = json.loads((BASE / "config.json").read_text())
    results.append(check("optin_enabled = false after disable",
                         cfg_after2.get("optin_enabled") is False,
                         str(cfg_after2.get("optin_enabled"))))

    # Restore original state
    SETTINGS.write_text(orig_settings)
    (BASE / "config.json").write_text(orig_cfg)

    print()
    print(SEP)

    # ── 7. context_uploader.py — Supabase upload ──────────────────────────────
    print()
    print("  7 — context_uploader.py (transcript read → Supabase upload)")
    print()

    uploader_sid = f"test-upload-{int(time.time())}"

    # Write a fake transcript JSONL with a real user message
    fake_transcript = tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False)
    fake_lines = [
        json.dumps({
            "type": "user",
            "uuid": "aaa",
            "parentUuid": None,
            "timestamp": "2026-06-14T12:00:00.000Z",
            "sessionId": uploader_sid,
            "cwd": "/tmp/testproject",
            "gitBranch": "main",
            "version": "2.1.177",
            "message": {
                "role": "user",
                "content": "How do I implement a binary search tree in TypeScript?"
            }
        }),
        json.dumps({
            "type": "assistant",
            "uuid": "bbb",
            "parentUuid": "aaa",
            "timestamp": "2026-06-14T12:00:05.000Z",
            "sessionId": uploader_sid,
            "cwd": "/tmp/testproject",
            "gitBranch": "main",
            "version": "2.1.177",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Here is how you'd implement it..."}]
            }
        }),
    ]
    fake_transcript.write("\n".join(fake_lines) + "\n")
    fake_transcript.flush()
    fake_transcript.close()

    # Seed a context cache for the uploader to read
    _ctx.write_cache({"typescript", "javascript"}, ["Edit"], [".ts"], uploader_sid)

    # Create a temp config with optin_enabled = true
    tmp_cfg = {**cfg, "optin_enabled": True, "user_id": cfg["user_id"]}
    tmp_cfg_path = Path(tempfile.mktemp(suffix=".json"))
    tmp_cfg_path.write_text(json.dumps(tmp_cfg))

    # Patch CFG_FILE env and run uploader
    uploader_stdin = json.dumps({
        "session_id":      uploader_sid,
        "transcript_path": fake_transcript.name,
        "cwd":             "/tmp/testproject",
    })

    env = os.environ.copy()
    env["TERM_SESSION_ID"] = uploader_sid  # so _ctx uses the same session key

    # Temporarily swap config file
    real_cfg_bak = CFG_FILE.read_text()
    CFG_FILE.write_text(json.dumps(tmp_cfg))

    proc2 = subprocess.run(
        [sys.executable, str(BASE / "context_uploader.py")],
        input=uploader_stdin, capture_output=True, text=True, timeout=10, env=env,
    )
    CFG_FILE.write_text(real_cfg_bak)  # restore
    Path(fake_transcript.name).unlink(missing_ok=True)
    tmp_cfg_path.unlink(missing_ok=True)

    results.append(check("context_uploader.py exits cleanly",
                         proc2.returncode == 0,
                         proc2.stderr[:80] if proc2.stderr else "ok"))

    # Verify the row landed in Supabase
    time.sleep(1)
    rows = api(cfg, "GET", "session_contexts",
               params=f"?session_id=eq.{uploader_sid}&select=session_id,tech_stack,prompt_snippet,tools_used")
    results.append(check("Row uploaded to session_contexts",
                         bool(rows), f"{len(rows) if rows else 0} rows"))
    if rows:
        row = rows[0]
        results.append(check("tech_stack contains typescript",
                             "typescript" in (row.get("tech_stack") or []),
                             str(row.get("tech_stack"))))
        results.append(check("prompt_snippet captured from transcript",
                             bool(row.get("prompt_snippet")) and "binary search" in row.get("prompt_snippet", ""),
                             repr(row.get("prompt_snippet", "")[:60])))
        results.append(check("tools_used recorded",
                             bool(row.get("tools_used")),
                             str(row.get("tools_used"))))

    # Cleanup Supabase test row
    try:
        api(cfg, "DELETE", "session_contexts",
            params=f"?session_id=eq.{uploader_sid}")
    except Exception:
        pass

    print()
    print(SEP)

    # ── 8. Supabase session_contexts table query ───────────────────────────────
    print()
    print("  8 — Supabase session_contexts table schema verification")
    print()

    # Insert a row via the API to verify schema
    test_ctx_sid = f"schema-test-{int(time.time())}"
    try:
        api(cfg, "POST", "session_contexts", {
            "user_id":         cfg["user_id"],
            "session_id":      test_ctx_sid,
            "cwd_hash":        "abcdef1234567890",
            "tech_stack":      ["python", "docker"],
            "tools_used":      ["Bash", "Edit"],
            "file_extensions": [".py", ".yml"],
            "prompt_snippet":  "Fix the authentication bug",
        })
        schema_ok = True
    except Exception as e:
        schema_ok = False
        print(f"  Insert error: {e}")

    results.append(check("session_contexts insert via anon key works", schema_ok))

    rows2 = api(cfg, "GET", "session_contexts",
                params=f"?session_id=eq.{test_ctx_sid}&select=*")
    results.append(check("session_contexts select works",
                         bool(rows2) and rows2[0]["session_id"] == test_ctx_sid,
                         f"{len(rows2) if rows2 else 0} rows"))

    # Cleanup
    try:
        api(cfg, "DELETE", "session_contexts", params=f"?session_id=eq.{test_ctx_sid}")
    except Exception:
        pass

    print()
    print(SEP)

    # ── Cleanup temp cache files ───────────────────────────────────────────────
    for sid in [test_sid, test_sid + "_stale", test_sid + "_hook", hook_sid, uploader_sid]:
        try:
            _ctx._cache_path(sid).unlink(missing_ok=True)
        except Exception:
            pass

    print()
    passed = sum(1 for r in results if r)
    total  = len(results)
    if passed == total:
        print(f"  All {total} checks passed.")
    else:
        print(f"  {passed}/{total} checks passed — see FAIL lines above.")
    print()


if __name__ == "__main__":
    main()
