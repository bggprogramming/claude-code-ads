#!/usr/bin/env python3
"""
Codex panel injector (opt-in, reversible) — the "kickback" in-panel surface.

Injects a clickable sponsor bar into OpenAI's Codex VS Code extension webview by:
  1. appending our Supabase origin to the webview CSP `connect-src` (so the
     injected script may call ad-feed / track-event),
  2. writing webview/cca-inject.js (renders the bar; your user_id baked in so
     earnings credit you; logs impression + vscode_click),
  3. adding one <script type="module" src="./cca-inject.js"> to webview/index.html.

SAFE: every edited file is backed up to <file>.cca-bak before the first change,
the patch is marker-guarded (idempotent), and `--revert` restores everything.

Pinned to the installed extension build — an extension update can overwrite the
bundle and silently disable this; just re-run to re-apply.

  python3 inject_codex_panel.py            # patch
  python3 inject_codex_panel.py --revert   # restore original files
  python3 inject_codex_panel.py --status   # show state
"""
import json
import sys
from pathlib import Path

SUPA = "https://gpbrzpyvzlzwvvymgeyk.supabase.co"
KEY  = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdwYnJ6cHl2"
        "emx6d3Z2eW1nZXlrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE0NjAwNDIsImV4cCI6MjA5NzAzNjA0Mn0"
        ".Wh60a8XyYCeKlOJn7HJOMpipTTHmzCRBaH3cEQ0C-vc")
BASE = Path(__file__).parent

EXT_GLOBS = ["openai.chatgpt-*", "openai.codex-*", "openai.*chatgpt*", "*codex*"]
EXT_ROOTS = [Path.home() / ".vscode" / "extensions",
             Path.home() / ".cursor" / "extensions",
             Path.home() / ".vscode-insiders" / "extensions"]

CSP_FIND = 'connect-src ${n.join(" ")}'
CSP_REPL = 'connect-src ${n.join(" ")} ' + SUPA
HTML_MARK = "<!-- cca-inject -->"
HTML_TAG  = '    <script type="module" crossorigin src="./cca-inject.js"></script>\n    ' + HTML_MARK + "\n"

INJECT_JS = r"""// claude-code-ads — injected Codex panel sponsor bar (remove via inject_codex_panel.py --revert)
(function(){
  try {
    if (window.__ccaLoaded) return; window.__ccaLoaded = true;
    var SUPA=%SUPA%, KEY=%KEY%, UID=%UID%, LVL=%LVL%;
    var FEED=SUPA+"/functions/v1/ad-feed", TRACK=SUPA+"/functions/v1/track-event";
    var bar=document.createElement("div"); bar.setAttribute("data-cca","1");
    bar.style.cssText="position:fixed;left:0;right:0;bottom:0;z-index:2147483647;"
      +"display:flex;align-items:center;gap:8px;padding:6px 10px;box-sizing:border-box;"
      +"font:12px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
      +"background:rgba(10,10,12,.92);border-top:1px solid rgba(255,255,255,.08);color:#8a8a92";
    var a=document.createElement("a"); a.target="_blank"; a.rel="noopener";
    a.style.cssText="color:#b4ff69;text-decoration:none;flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis";
    bar.appendChild(a);
    function mount(){ if(document.body && !bar.isConnected) document.body.appendChild(bar); }
    var cur=null;
    function track(ev,ad){ try{ fetch(TRACK,{method:"POST",headers:{"apikey":KEY,"Authorization":"Bearer "+KEY,"Content-Type":"application/json"},
      body:JSON.stringify({ad_id:ad.id,ad_text:ad.text||"",event:ev,surface:ev==="click"?"vscode_click":"vscode_panel",user_id:UID,share_level:LVL,variant:"default"})}); }catch(e){} }
    function pick(ads){ var t=0,i; for(i=0;i<ads.length;i++)t+=ads[i].weight||1; var r=Math.random()*t;
      for(i=0;i<ads.length;i++){ r-=ads[i].weight||1; if(r<=0) return ads[i]; } return ads[ads.length-1]; }
    function render(ad){ cur=ad; a.textContent="💸 "+(ad.text||"")+" ↗"; a.href=ad.url||"#"; mount(); track("impression",ad); }
    a.addEventListener("click",function(){ if(cur) track("click",cur); });
    function load(){ fetch(FEED,{headers:{"apikey":KEY}}).then(function(r){return r.json();})
      .then(function(d){ var ads=(d&&d.ads)||d; if(ads&&ads.length) render(pick(ads)); }).catch(function(){}); }
    if(document.body) load(); else document.addEventListener("DOMContentLoaded",load);
    setInterval(load,45000);
  } catch(e) {}
})();
"""


def load_identity():
    for f in (BASE / "config.json", Path.home() / ".claude-code-ads.json"):
        try:
            c = json.loads(f.read_text())
            if c.get("user_id"):
                return c["user_id"], int(c.get("share_level", 1 if c.get("optin_enabled") else 0))
        except Exception:
            pass
    return None, 0


def find_ext():
    for root in EXT_ROOTS:
        if not root.is_dir():
            continue
        for g in EXT_GLOBS:
            for d in sorted(root.glob(g)):
                if (d / "webview" / "index.html").exists() and (d / "out" / "extension.js").exists():
                    return d
    return None


def _backup(p: Path):
    bak = p.with_suffix(p.suffix + ".cca-bak")
    if not bak.exists():
        bak.write_bytes(p.read_bytes())


def _restore(p: Path):
    bak = p.with_suffix(p.suffix + ".cca-bak")
    if bak.exists():
        p.write_bytes(bak.read_bytes())
        bak.unlink()
        return True
    return False


def patch(ext: Path):
    uid, lvl = load_identity()
    extjs = ext / "out" / "extension.js"
    html  = ext / "webview" / "index.html"
    inj   = ext / "webview" / "cca-inject.js"

    # 1. CSP connect-src
    js = extjs.read_text(encoding="utf-8", errors="replace")
    if SUPA in js and CSP_REPL in js:
        print("  · CSP already patched")
    elif CSP_FIND in js:
        _backup(extjs)
        extjs.write_text(js.replace(CSP_FIND, CSP_REPL, 1), encoding="utf-8")
        print("  ✓ CSP connect-src extended")
    else:
        print("  ✗ CSP anchor not found — extension build changed; aborting (no changes).")
        return False

    # 2. inject script
    js_body = (INJECT_JS
               .replace("%SUPA%", json.dumps(SUPA))
               .replace("%KEY%",  json.dumps(KEY))
               .replace("%UID%",  json.dumps(uid))
               .replace("%LVL%",  json.dumps(lvl)))
    inj.write_text(js_body, encoding="utf-8")
    print(f"  ✓ wrote {inj.name}  (user_id={'set' if uid else 'anonymous'}, share_level={lvl})")

    # 3. HTML script tag
    h = html.read_text(encoding="utf-8", errors="replace")
    if HTML_MARK in h:
        print("  · index.html already patched")
    else:
        _backup(html)
        html.write_text(h.replace("</head>", HTML_TAG + "  </head>", 1), encoding="utf-8")
        print("  ✓ index.html script tag injected")

    print("\n  Done. Reload the editor window (Cmd+Shift+P → Reload Window) to load it.")
    print("  Revert anytime: python3 ~/.claude/ads/inject_codex_panel.py --revert")
    return True


def revert(ext: Path):
    n = 0
    for p in (ext / "out" / "extension.js", ext / "webview" / "index.html"):
        if _restore(p):
            n += 1; print(f"  ✓ restored {p.name}")
    inj = ext / "webview" / "cca-inject.js"
    if inj.exists():
        inj.unlink(); print("  ✓ removed cca-inject.js")
    print(f"  Reverted {n} file(s). Reload the editor window." if n else "  Nothing to revert.")


def status(ext: Path):
    html = (ext / "webview" / "index.html").read_text(errors="replace")
    js   = (ext / "out" / "extension.js").read_text(errors="replace")
    print(f"  extension: {ext.name}")
    print(f"  CSP patched:   {SUPA in js}")
    print(f"  HTML injected: {HTML_MARK in html}")
    print(f"  inject.js:     {(ext / 'webview' / 'cca-inject.js').exists()}")


def main():
    ext = find_ext()
    if not ext:
        print("  No Codex/ChatGPT VS Code extension found. Install it, then re-run.")
        sys.exit(0)
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--revert":
        revert(ext)
    elif arg == "--status":
        status(ext)
    else:
        print(f"  Patching {ext.name} …")
        patch(ext)


if __name__ == "__main__":
    main()
