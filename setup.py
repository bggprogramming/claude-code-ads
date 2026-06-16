#!/usr/bin/env python3
"""
First-time user registration for the referral system.

Generates a unique user_id and referral_code, writes them to config.json,
and registers the user in Supabase. Idempotent — safe to run multiple times.

Usage:
  python3 setup.py                   # fresh install (asks to sign in if you
                                     #   already use Mango on another machine)
  python3 setup.py --ref abc123      # install via a friend's referral link
  python3 setup.py --signin abc123   # link THIS device to your existing account
"""
import argparse
import json
import random
import ssl
import string
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import certifi

BASE     = Path(__file__).parent
CFG_FILE = BASE / "config.json"
SSL_CTX  = ssl.create_default_context(cafile=certifi.where())

CHARS    = string.ascii_lowercase + string.digits   # base-36 alphabet


def gen_referral_code():
    """6-char base-36 code derived from a fresh UUID."""
    n = int(uuid.uuid4().hex, 16)
    code = ""
    for _ in range(6):
        code += CHARS[n % 36]
        n //= 36
    return code


def load_config():
    try:
        with open(CFG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data):
    tmp = CFG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(CFG_FILE)


def register_supabase(cfg):
    """Insert user row — Supabase ignores duplicates via ON CONFLICT DO NOTHING."""
    url     = f"{cfg['supabase_url']}/rest/v1/users"
    payload = json.dumps({
        "id":            cfg["user_id"],
        "referral_code": cfg["referral_code"],
        "referred_by":   cfg.get("referred_by") or None,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "apikey":        cfg["supabase_key"],
        "Authorization": f"Bearer {cfg['supabase_key']}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=ignore-duplicates,return=minimal",
    }, method="POST")
    try:
        urllib.request.urlopen(req, timeout=6, context=SSL_CTX)
        return True
    except Exception as e:
        print(f"  Warning: could not register online ({e}). Will retry on next run.", file=sys.stderr)
        return False


def validate_ref_code(ref_code, cfg):
    """Check that the referral code exists in Supabase (basic fraud guard)."""
    if not ref_code:
        return True
    url = f"{cfg['supabase_url']}/rest/v1/users?referral_code=eq.{ref_code}&select=referral_code"
    req = urllib.request.Request(url, headers={
        "apikey":        cfg["supabase_key"],
        "Authorization": f"Bearer {cfg['supabase_key']}",
    })
    try:
        resp  = urllib.request.urlopen(req, timeout=4, context=SSL_CTX)
        rows  = json.loads(resp.read())
        return len(rows) > 0
    except Exception:
        return True   # be lenient on network failure


def _ask(prompt):
    """Read one line, preferring the controlling terminal so it works even under
    `curl ... | bash`. Returns '' when there is no terminal."""
    try:
        if sys.stdin.isatty():
            return input(prompt)
        with open("/dev/tty") as tty:
            sys.stdout.write(prompt); sys.stdout.flush()
            return tty.readline()
    except Exception:
        return ""


def link_device(cfg, account_code):
    """Fold this freshly-registered device into an existing account so earnings
    aggregate in the portal. Both codes are required (each is that account's
    credential), so you can only link your own devices."""
    url  = f"{cfg['supabase_url']}/functions/v1/link-device"
    body = json.dumps({"code": account_code, "device_code": cfg["referral_code"]}).encode()
    req  = urllib.request.Request(url, data=body,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.loads(urllib.request.urlopen(req, timeout=8, context=SSL_CTX).read())
    except urllib.error.HTTPError as e:
        try:    return json.loads(e.read())
        except Exception: return {"error": f"http {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def do_signin(cfg, account_code):
    """Link this device into `account_code` and remember the canonical account."""
    account_code = "".join(c for c in (account_code or "").lower() if c.isalnum())
    if not account_code:
        return False
    if account_code == cfg.get("referral_code"):
        print("  That's this device's own code — nothing to link.")
        return False
    res = link_device(cfg, account_code)
    if res.get("ok"):
        cfg["account_code"] = res.get("into", account_code)
        save_config(cfg)
        print(f"  ✓ Signed in — this device now rolls up into "
              f"{cfg['account_code']} ({res.get('devices', '?')} devices, "
              f"${float(res.get('total_dollars', 0)):.2f} total).")
        return True
    err = res.get("error", "unknown error")
    if err == "device code not found":
        err = "this device isn't registered yet — try again in a moment"
    print(f"  Couldn't sign in to '{account_code}' ({err}). This device will track "
          f"on its own; you can link it anytime in your portal.")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="", help="Referral code from the person who sent you here")
    parser.add_argument("--signin", default="", help="Your own Mango code, to link this device to your existing account")
    args = parser.parse_args()

    cfg = load_config()

    # Already registered — show info, and honour an explicit --signin to link this
    # already-installed device into your account.
    if cfg.get("user_id") and cfg.get("referral_code"):
        print(f"  Already set up.")
        print(f"  Referral code: {cfg['referral_code']}")
        if cfg.get("account_code"):
            print(f"  Linked to:     {cfg['account_code']}")
        elif args.signin:
            do_signin(cfg, args.signin)
        _show_link(cfg.get("account_code") or cfg["referral_code"])
        return

    if not cfg.get("supabase_url") or not cfg.get("supabase_key"):
        print("Error: config.json missing supabase_url / supabase_key.", file=sys.stderr)
        sys.exit(1)

    ref_code = args.ref.strip().lower() or ""

    # Validate the referral code exists
    if ref_code:
        if not validate_ref_code(ref_code, cfg):
            print(f"  Warning: referral code '{ref_code}' not found. Continuing without it.")
            ref_code = ""
        else:
            print(f"  Referral code '{ref_code}' verified.")

    cfg["user_id"]       = str(uuid.uuid4())
    cfg["referral_code"] = gen_referral_code()
    cfg["referred_by"]   = ref_code or None

    save_config(cfg)
    print(f"  User ID:       {cfg['user_id']}")
    print(f"  Referral code: {cfg['referral_code']}")
    if ref_code:
        print(f"  Referred by:   {ref_code}")

    ok = register_supabase(cfg)
    if ok:
        print("  Registered.")
    try:
        sys.path.insert(0, str(BASE)); import funnel; funnel.log("registered")
    except Exception:
        pass

    # Sign in: if this is one of your own machines, link it to your existing
    # account so all your devices' earnings show as one total. (Skipped for
    # referral installs — those are genuinely new accounts.)
    signin_code = args.signin.strip().lower()
    if not signin_code and not ref_code:
        signin_code = _ask("  Already use Mango on another machine? Enter your code to "
                           "link this device to it (or press Enter to start fresh): ")
    if signin_code.strip():
        do_signin(cfg, signin_code)

    _show_link(cfg.get("account_code") or cfg["referral_code"])


def _show_link(code):
    print()
    print("  Your referral link:")
    print(f"  curl -fsSL https://raw.githubusercontent.com/bggprogramming/mango/main/install.sh | bash -s -- --ref {code}")
    print()
    print("  Share this — when someone you refer earns their first $5, you both get $10.")


if __name__ == "__main__":
    main()
