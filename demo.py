#!/usr/bin/env python3
"""
The "it worked" moment — shown once at the end of install (TTY only).
Renders a real ad line (from the live feed, contextually chosen) plus a tiny
earnings tick, so the user sees value in the first seconds instead of waiting
for a session. Purely cosmetic: writes nothing to the server.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

GREEN = "\033[38;5;156m"
PINK  = "\033[38;5;205m"
DIM   = "\033[2m"
B     = "\033[1m"
R     = "\033[0m"


def main():
    try:
        import context as _ctx
        import feed as _feed
        ads = _feed.load_ads()
        if not ads:
            return
        ctx = _ctx.get_context()
        ad  = _ctx.select_optimal(ads, ctx) or ads[0]
        text, _ = _ctx.select_copy(ad, ctx)
    except Exception:
        return

    print()
    print(f"  {B}Here's what you'll see while you code:{R}")
    print(f"  {DIM}{text} ↗{R}")
    print()

    if sys.stdout.isatty():
        try:
            for amt in (0.0008, 0.0017, 0.0026):
                sys.stdout.write(
                    f"\r  {GREEN}{B}＄{amt:.4f}{R} {DIM}earned — and it keeps climbing every session{R}   ")
                sys.stdout.flush()
                time.sleep(0.45)
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass
    print(f"  {GREEN}✓ You're live.{R} {DIM}It runs on its own — nothing else to do.{R}")
    print()


if __name__ == "__main__":
    main()
