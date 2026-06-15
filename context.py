#!/usr/bin/env python3
"""
Local project context detection for ad targeting.
All inference is local — no data leaves the machine without explicit opt-in.

Provides:
  - Filesystem-based tech stack detection (always-on)
  - Tool-use signal extraction (always-on, used in PostToolUse hook)
  - Session context cache shared across all scripts
  - Contextual weight boosting for ad selection
"""
import glob
import json
import os
import random
import time
from pathlib import Path

CACHE_TTL   = 3600   # 1 hour — context persists for a full dev session
BOOST       = 2.5    # contextual match multiplier

# ── Optimal-placement (contextual bandit) tuning ───────────────────────────────
# We rank the live ad library by EXPECTED VALUE per impression — the real ad-tech
# objective (eCPM = bid × predicted-CTR). Since the developer earns proportionally
# to the ad's price and a click pays CLICK_VALUE_MULT× an impression, maximizing
# EV maximizes both network revenue and developer earnings.
#
#   EV(ad | context) ≈ price · (1 + CLICK_VALUE_MULT · pCTR) · relevance
#
# pCTR is a Bayesian-smoothed click rate per (ad, context) drawn by THOMPSON
# SAMPLING from Beta(α,β): unproven ads are explored, proven winners exploited —
# automatically, with no separate explore schedule. Context stays on-device; only
# the aggregate per-ad/per-variant counts come from the feed, so privacy holds.
CLICK_VALUE_MULT = 50     # a click is worth ~50× an impression (matches track-event)
PRIOR_CTR        = 0.02   # prior belief about click-through rate (2%)
PRIOR_STRENGTH   = 40      # prior weight in pseudo-impressions (higher = more cautious)

# Filesystem signals: tag → file names to look for at the project root
STACK_FILES = {
    "javascript": ["package.json", ".eslintrc.js", ".eslintrc.json", ".babelrc",
                   ".babelrc.js", ".nvmrc", ".node-version"],
    "typescript": ["tsconfig.json", "tsconfig.base.json"],
    "python":     ["requirements.txt", "requirements-dev.txt", "pyproject.toml",
                   "setup.py", "setup.cfg", "Pipfile", ".python-version", "poetry.lock"],
    "rust":       ["Cargo.toml", "Cargo.lock"],
    "go":         ["go.mod", "go.sum"],
    "docker":     ["Dockerfile", "docker-compose.yml", "docker-compose.yaml",
                   "Dockerfile.dev", "Dockerfile.prod", ".dockerignore"],
    "infra":      [".github", "terraform.tf", "main.tf", "variables.tf",
                   "Pulumi.yaml", "serverless.yml", "serverless.yaml",
                   "k8s", "kubernetes", "cdk.json", "pulumi.yaml"],
    "java":       ["pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle"],
    "ruby":       ["Gemfile", "Gemfile.lock", "Rakefile", ".ruby-version"],
    "elixir":     ["mix.exs", "mix.lock"],
}

# File extension → tags
EXT_TAGS = {
    ".ts":   ["typescript", "javascript"],
    ".tsx":  ["typescript", "javascript"],
    ".mts":  ["typescript", "javascript"],
    ".js":   ["javascript"],
    ".jsx":  ["javascript"],
    ".mjs":  ["javascript"],
    ".cjs":  ["javascript"],
    ".py":   ["python"],
    ".rs":   ["rust"],
    ".go":   ["go"],
    ".rb":   ["ruby"],
    ".ex":   ["elixir"],
    ".exs":  ["elixir"],
    ".java": ["java"],
    ".kt":   ["java"],
    ".tf":   ["infra"],
    ".hcl":  ["infra"],
}

# Shell command prefix → tags
CMD_TAGS = {
    "npm ":      ["javascript"],
    "npx ":      ["javascript"],
    "yarn ":     ["javascript"],
    "pnpm ":     ["javascript"],
    "node ":     ["javascript"],
    "tsc ":      ["typescript"],
    "ts-node":   ["typescript"],
    "cargo ":    ["rust"],
    "rustc ":    ["rust"],
    "go ":       ["go"],
    "pip ":      ["python"],
    "pip3 ":     ["python"],
    "python ":   ["python"],
    "python3 ":  ["python"],
    "poetry ":   ["python"],
    "uv ":       ["python"],
    "docker ":   ["docker"],
    "docker-compose": ["docker"],
    "kubectl ":  ["infra"],
    "helm ":     ["infra"],
    "terraform ":["infra"],
    "pulumi ":   ["infra"],
    "bundle ":   ["ruby"],
    "rails ":    ["ruby"],
    "mix ":      ["elixir"],
    "mvn ":      ["java"],
    "gradle ":   ["java"],
}


# ── Session ID ────────────────────────────────────────────────────────────────

def _session_id():
    return (
        os.environ.get("TERM_SESSION_ID")
        or os.environ.get("TMUX_PANE")
        or f"pid-{os.getppid()}"
    )


def _cache_path(session_id=None):
    sid = session_id or _session_id()
    # Sanitize for safe filename
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(sid))
    return Path(f"/tmp/claude-ads-ctx-{safe}.json")


# ── Filesystem detection ──────────────────────────────────────────────────────

def detect_from_filesystem(cwd=None):
    """
    Detect tech stack by scanning project root files.
    Fast (no recursion), local, always-on.
    """
    cwd = Path(cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    tags = set()

    for tag, files in STACK_FILES.items():
        for fname in files:
            if (cwd / fname).exists():
                tags.add(tag)
                break

    # Refine: if package.json exists check for TypeScript dependency
    if "javascript" in tags:
        pkg = cwd / "package.json"
        try:
            data = json.loads(pkg.read_text())
            all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if any(k in all_deps for k in ("typescript", "ts-node", "tsx", "@types/node")):
                tags.add("typescript")
        except Exception:
            pass

    return tags


# ── Tool-derived signals ──────────────────────────────────────────────────────

def tags_from_tool(tool_name, tool_input):
    """Extract tech stack signals from a PostToolUse event (no file content, just path/command)."""
    tags = set()
    exts = set()

    if not isinstance(tool_input, dict):
        return tags, exts

    file_path = tool_input.get("file_path", "")
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in EXT_TAGS:
            tags.update(EXT_TAGS[ext])
            exts.add(ext)
        base = os.path.basename(file_path).lower()
        if "dockerfile" in base:
            tags.add("docker")
        if "docker-compose" in base:
            tags.add("docker")
        if base.endswith(".tf") or "terraform" in base:
            tags.add("infra")
        if base.endswith(".tf"):
            exts.add(".tf")

    command = (tool_input.get("command", "") or "").strip().lower()
    if command:
        for prefix, cmd_tags in CMD_TAGS.items():
            if command.startswith(prefix) or f" {prefix}" in command:
                tags.update(cmd_tags)
                break

    return tags, exts


# ── Session context cache ─────────────────────────────────────────────────────

def read_cache(session_id=None):
    """Read cached context. Returns (tags_set, tools_list, exts_list) or None."""
    try:
        p = _cache_path(session_id)
        if p.exists():
            data = json.loads(p.read_text())
            if time.time() - data.get("ts", 0) < CACHE_TTL:
                return (
                    set(data.get("tags", [])),
                    list(data.get("tools", [])),
                    list(data.get("extensions", [])),
                )
    except Exception:
        pass
    return None


def write_cache(tags, tools=None, extensions=None, session_id=None):
    """Write context to session cache."""
    try:
        _cache_path(session_id).write_text(json.dumps({
            "tags":       list(tags),
            "tools":      list(tools or []),
            "extensions": list(extensions or []),
            "ts":         time.time(),
        }))
    except Exception:
        pass


def merge_into_cache(new_tags, new_tools=None, new_exts=None, session_id=None):
    """Merge new signals into existing session cache (non-destructive)."""
    cached = read_cache(session_id)
    if cached:
        tags, tools, exts = cached
    else:
        tags, tools, exts = set(), [], []

    updated_tags = tags | (new_tags or set())
    updated_tools = list(set(tools) | set(new_tools or []))
    updated_exts  = list(set(exts)  | set(new_exts or []))

    if updated_tags != tags or len(updated_tools) != len(tools) or len(updated_exts) != len(exts):
        write_cache(updated_tags, updated_tools, updated_exts, session_id)

    return updated_tags, updated_tools, updated_exts


# ── Main API: get context for ad selection ────────────────────────────────────

def get_context(cwd=None, session_id=None):
    """
    Get current context tags for ad targeting.
    Checks session cache first; on miss, scans filesystem and seeds cache.
    """
    cached = read_cache(session_id)
    if cached is not None:
        return cached[0]  # just the tags set

    tags = detect_from_filesystem(cwd)
    write_cache(tags, session_id=session_id)
    return tags


# ── Ad selection ──────────────────────────────────────────────────────────────

def contextual_weight(ad, context_tags):
    """
    Effective rotation weight for an ad given the project context.
    Ads whose tags overlap the detected context get BOOST× the base weight.
    """
    base     = ad.get("weight", 1)
    ad_tags  = set(ad.get("tags", []))
    if ad_tags and context_tags and (ad_tags & context_tags):
        return base * BOOST
    return float(base)


def select_copy(ad, context_tags=None):
    """
    Select the best copy variant for the current context.
    Returns (text: str, variant_key: str).

    If the ad has use_variants=True and copy_variants, pick the best matching
    variant for the detected tech stack. Advertisers opt-in per-campaign.
    """
    variants = ad.get("copy_variants")
    if not variants or not ad.get("use_variants"):
        return ad.get("text", ""), "default"

    ctx = context_tags or set()
    # Check detected tags in order of specificity (longer/rarer tags first)
    priority = ["typescript", "rust", "go", "python", "javascript", "docker", "infra"]
    for tag in priority:
        if tag in ctx and tag in variants:
            return variants[tag], tag
    # Any remaining tag match
    for tag in ctx:
        if tag in variants:
            return variants[tag], tag

    default_text = variants.get("default", ad.get("text", ""))
    return default_text, "default"


def weighted_sample(pool, context_tags=None):
    """Weighted random selection with optional contextual boosting.
    (Kept for back-compat + as the fallback when no performance stats exist.)"""
    ctx = context_tags or set()
    total = sum(contextual_weight(a, ctx) for a in pool)
    if total <= 0:
        return pool[-1]
    r = random.random() * total
    for ad in pool:
        r -= contextual_weight(ad, ctx)
        if r <= 0:
            return ad
    return pool[-1]


# ── Optimal placement: expected-value (eCPM) ranking with Thompson sampling ────

def _beta_sample(alpha, beta):
    """Draw from Beta(alpha, beta) via two Gamma draws (Thompson sampling)."""
    try:
        x = random.gammavariate(max(alpha, 1e-6), 1.0)
        y = random.gammavariate(max(beta, 1e-6), 1.0)
        return x / (x + y) if (x + y) > 0 else PRIOR_CTR
    except Exception:
        return PRIOR_CTR


def expected_value(ad, context_tags=None, variant=None):
    """Expected developer revenue per impression for this ad in this context.

    Uses the ad's price (cpm ∝ bid) × (1 + CLICK_VALUE_MULT · pCTR), where pCTR is
    Thompson-sampled from the ad's measured clicks/impressions — preferring the
    stats for the *variant we'd actually show* (which encodes the context), then
    the ad's global stats, then a weak prior. A matching tag adds a relevance lift.
    """
    ctx   = context_tags or set()
    price = float(ad.get("cpm", 20) or 20)

    perf  = ad.get("perf") or {}
    stats = None
    if variant and variant != "default":
        stats = (perf.get("variants") or {}).get(variant)
    if not stats:
        stats = {"imp": perf.get("imp", 0), "clk": perf.get("clk", 0)}

    imp = max(0, int(stats.get("imp", 0) or 0))
    clk = max(0, min(imp, int(stats.get("clk", 0) or 0)))

    alpha = PRIOR_CTR * PRIOR_STRENGTH + clk
    beta  = (1.0 - PRIOR_CTR) * PRIOR_STRENGTH + (imp - clk)
    pctr  = _beta_sample(alpha, beta)

    ev = price * (1.0 + CLICK_VALUE_MULT * pctr)

    ad_tags = set(ad.get("tags", []))
    if ad_tags and ctx and (ad_tags & ctx):
        ev *= BOOST
    return max(ev, 1e-6)


def select_optimal(pool, context_tags=None):
    """Pick an ad from the live library to maximize expected value, with built-in
    exploration. Samples proportionally to Thompson-sampled EV so high-value ads
    win most impressions while unproven ones still get explored. Falls back to a
    uniform pick only if scoring fails."""
    if not pool:
        return None
    ctx    = context_tags or set()
    scored = []
    for ad in pool:
        _, variant = select_copy(ad, ctx)
        scored.append((expected_value(ad, ctx, variant), ad))
    total = sum(s for s, _ in scored)
    if total <= 0:
        return pool[-1]
    r = random.random() * total
    for s, ad in scored:
        r -= s
        if r <= 0:
            return ad
    return scored[-1][1]
