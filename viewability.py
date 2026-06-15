#!/usr/bin/env python3
"""
Ad viewability check: only count an impression when the terminal window is
actually on-screen and not covered by another window.

Focus is NOT required — the window just has to be visible (>= VIEW_THRESHOLD of
its area unoccluded). Uses macOS Quartz CGWindowList (z-ordered on-screen windows;
needs no Screen Recording permission since we read bounds/owner/layer, not titles).

Result is cached briefly so the high-frequency statusLine doesn't pay the cost on
every render. Degrades gracefully: if it can't determine state (non-macOS, Quartz
missing, no window found), it returns True so legitimate impressions aren't lost.
"""
import json
import os
import sys
import time
from pathlib import Path

VIEW_THRESHOLD = 0.5          # >= 50% of the window must be visible
CACHE_TTL      = 2.0          # seconds — reuse the result across rapid renders
DEFAULT_WHEN_UNKNOWN = True   # don't drop impressions we genuinely can't verify

# TERM_PROGRAM → candidate macOS app owner names in CGWindowList.
_TERM_OWNERS = {
    "iTerm.app":      ["iTerm2"],
    "Apple_Terminal": ["Terminal"],
    "vscode":         ["Code", "Cursor", "Windsurf", "Code - Insiders", "VSCodium"],
    "WarpTerminal":   ["Warp", "Warp.dev", "WarpPreview"],
    "Hyper":          ["Hyper"],
    "WezTerm":        ["WezTerm", "wezterm-gui"],
    "ghostty":        ["Ghostty", "ghostty"],
}
_ALL_OWNERS = ["Terminal", "iTerm2", "Code", "Cursor", "Windsurf", "Warp",
               "Alacritty", "kitty", "WezTerm", "Hyper", "Ghostty", "tmux"]


def _sid():
    return os.environ.get("TERM_SESSION_ID") or os.environ.get("TMUX_PANE") or str(os.getppid())


def _cache_path():
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in _sid())
    return Path(f"/tmp/claude-ads-view-{safe}.json")


def _owner_candidates():
    tp = os.environ.get("TERM_PROGRAM", "")
    return _TERM_OWNERS.get(tp, _ALL_OWNERS)


def _union_area(rects):
    """Area of the union of axis-aligned rects [(x0,y0,x1,y1), ...] via x-slabs."""
    if not rects:
        return 0.0
    xs = sorted(set([r[0] for r in rects] + [r[2] for r in rects]))
    total = 0.0
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        w = x1 - x0
        if w <= 0:
            continue
        ys = sorted((r[1], r[3]) for r in rects if r[0] <= x0 and r[2] >= x1)
        cov = 0.0
        cur = None
        for a, b in ys:
            if cur is None:
                cur = [a, b]
            elif a <= cur[1]:
                cur[1] = max(cur[1], b)
            else:
                cov += cur[1] - cur[0]
                cur = [a, b]
        if cur:
            cov += cur[1] - cur[0]
        total += w * cov
    return total


def _compute_macos():
    """Return True/False for viewability, or None if undeterminable."""
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly,
            kCGWindowListExcludeDesktopElements, kCGNullWindowID,
            CGDisplayIsAsleep, CGMainDisplayID,
        )
    except Exception:
        return None

    try:
        if CGDisplayIsAsleep(CGMainDisplayID()):
            return False  # display asleep → not visible
    except Exception:
        pass

    try:
        opts = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        wins = CGWindowListCopyWindowInfo(opts, kCGNullWindowID)  # front-to-back
    except Exception:
        return None
    if not wins:
        return None

    candidates = set(_owner_candidates())

    def bounds(w):
        b = w.get("kCGWindowBounds") or {}
        x, y = float(b.get("X", 0)), float(b.get("Y", 0))
        return (x, y, x + float(b.get("Width", 0)), y + float(b.get("Height", 0)))

    # Find the frontmost normal terminal window.
    target_idx = None
    target = None
    for i, w in enumerate(wins):
        owner = w.get("kCGWindowOwnerName", "")
        layer = int(w.get("kCGWindowLayer", 0) or 0)
        bx0, by0, bx1, by1 = bounds(w)
        area = (bx1 - bx0) * (by1 - by0)
        if owner in candidates and layer == 0 and area >= 200 * 120:
            target_idx, target = i, (bx0, by0, bx1, by1)
            break

    if target is None:
        # No on-screen terminal window → minimized/hidden/another Space.
        return False

    tx0, ty0, tx1, ty1 = target
    t_area = (tx1 - tx0) * (ty1 - ty0)
    if t_area <= 0:
        return None

    # Occluders: windows in front of the target that overlap it.
    occ = []
    for w in wins[:target_idx]:
        if int(w.get("kCGWindowAlpha", 1) or 1) == 0:
            continue
        ox0, oy0, ox1, oy1 = bounds(w)
        # clip to target
        cx0, cy0 = max(tx0, ox0), max(ty0, oy0)
        cx1, cy1 = min(tx1, ox1), min(ty1, oy1)
        if cx1 > cx0 and cy1 > cy0:
            occ.append((cx0, cy0, cx1, cy1))

    covered = _union_area(occ)
    visible_fraction = 1.0 - (covered / t_area)
    return visible_fraction >= VIEW_THRESHOLD


def is_viewable():
    """True if the terminal window is on-screen and >= VIEW_THRESHOLD visible."""
    # Cache: avoid re-importing Quartz on every rapid statusLine render.
    cp = _cache_path()
    try:
        if cp.exists():
            data = json.loads(cp.read_text())
            if time.time() - data.get("ts", 0) < CACHE_TTL:
                return bool(data.get("viewable", DEFAULT_WHEN_UNKNOWN))
    except Exception:
        pass

    result = None
    if sys.platform == "darwin":
        result = _compute_macos()
    viewable = DEFAULT_WHEN_UNKNOWN if result is None else result

    try:
        cp.write_text(json.dumps({"ts": time.time(), "viewable": viewable}))
    except Exception:
        pass
    return viewable


if __name__ == "__main__":
    print("viewable:", is_viewable())
