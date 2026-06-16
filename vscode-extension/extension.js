// @ts-check
'use strict';

const vscode  = require('vscode');
const https   = require('https');
const http    = require('http');
const os      = require('os');
const path    = require('path');
const fs      = require('fs');
const crypto  = require('crypto');

// ── Config ──────────────────────────────────────────────────────────────────

const SUPABASE_URL  = 'https://gpbrzpyvzlzwvvymgeyk.supabase.co';
const SUPABASE_KEY  = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdwYnJ6cHl2emx6d3Z2eW1nZXlrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE0NjAwNDIsImV4cCI6MjA5NzAzNjA0Mn0.Wh60a8XyYCeKlOJn7HJOMpipTTHmzCRBaH3cEQ0C-vc';
const FEED_URL      = 'https://raw.githubusercontent.com/bggprogramming/mango/main/ads.json';
const REFRESH_MS    = 30_000;
const IDLE_MS       = 5 * 60_000; // stop counting impressions after 5 min of no activity
const CLAUDE_CFG    = path.join(os.homedir(), '.claude', 'ads', 'config.json');
const VSCODE_CFG    = path.join(os.homedir(), '.claude-code-ads.json');
const STATUSBAR_CPM = 25; // default CPM for VS Code status bar

// ── User identity ────────────────────────────────────────────────────────────

function getOrCreateUser() {
  // Prefer existing Claude Code config (same user_id + referral_code)
  try {
    const cfg = JSON.parse(fs.readFileSync(CLAUDE_CFG, 'utf8'));
    if (cfg.user_id) return { userId: cfg.user_id, referralCode: cfg.referral_code || null };
  } catch {}

  // VS Code-only users: create/load standalone config
  try {
    const cfg = JSON.parse(fs.readFileSync(VSCODE_CFG, 'utf8'));
    if (cfg.user_id) return { userId: cfg.user_id, referralCode: cfg.referral_code || null };
  } catch {}

  // Brand new user
  const userId = crypto.randomUUID();
  const refCode = Buffer.from(crypto.randomBytes(4)).toString('base64url').slice(0, 6).toLowerCase();
  const cfg = { user_id: userId, referral_code: refCode, created_at: new Date().toISOString(), source: 'vscode' };
  try { fs.writeFileSync(VSCODE_CFG, JSON.stringify(cfg, null, 2)); } catch {}

  // Register in Supabase
  supabasePost('/rest/v1/users', {
    id: userId, referral_code: refCode, referred_by: null, milestone_hit: false,
  }).catch(() => {});

  return { userId, referralCode: refCode };
}

// ── HTTP helpers ─────────────────────────────────────────────────────────────

function httpsGet(url, timeoutMs = 2000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: timeoutMs }, res => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
  });
}

function supabasePost(path, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const url     = new URL(SUPABASE_URL + path);
    const opts    = {
      hostname: url.hostname, port: 443, path: url.pathname,
      method: 'POST',
      headers: {
        'apikey': SUPABASE_KEY, 'Authorization': `Bearer ${SUPABASE_KEY}`,
        'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload),
        'Prefer': 'return=minimal',
      },
    };
    const req = https.request(opts, res => {
      res.resume();
      resolve(res.statusCode);
    });
    req.on('error', reject);
    req.write(payload);
    req.end();
  });
}

// ── Ad feed ──────────────────────────────────────────────────────────────────

async function loadAds() {
  // Auction feed: built-in house ads + live paid campaigns, bid-ordered.
  const cache = path.join(os.tmpdir(), 'claude-ads-feed.json');
  try {
    const st = fs.statSync(cache);
    if (Date.now() - st.mtimeMs < 60_000) {           // 60s cache
      const data = JSON.parse(fs.readFileSync(cache, 'utf8'));
      if (Array.isArray(data) && data.length > 0) return data;
    }
  } catch {}

  try {
    const raw  = await httpsGet(`${SUPABASE_URL}/functions/v1/ad-feed`, 2000);
    const body = JSON.parse(raw);
    const ads  = Array.isArray(body) ? body : body.ads;   // {ads, hash}
    if (Array.isArray(ads) && ads.length > 0) {
      try { fs.writeFileSync(cache, JSON.stringify(ads)); } catch {}
      return ads;
    }
  } catch {}

  // Fallbacks: legacy GitHub feed, then nothing.
  try {
    const data = JSON.parse(await httpsGet(FEED_URL, 2000));
    if (Array.isArray(data) && data.length > 0) return data;
  } catch {}
  return [];
}

function weightedSample(ads) {
  const total = ads.reduce((s, a) => s + (a.weight || 1), 0);
  let r = Math.random() * total;
  for (const ad of ads) { r -= (ad.weight || 1); if (r <= 0) return ad; }
  return ads[ads.length - 1];
}

// ── Optimal placement: same contextual Thompson-sampling bandit as the CLI ─────
// EV = price · (1 + 50·pCTR) · relevance, pCTR ~ Beta(α,β) over measured clicks.
const CLICK_VALUE_MULT = 50, PRIOR_CTR = 0.02, PRIOR_STRENGTH = 40, BOOST = 2.5;
const VARIANT_PRIORITY = ['typescript', 'rust', 'go', 'python', 'javascript', 'docker', 'infra'];

function _gauss() { let u = 0, v = 0; while (!u) u = Math.random(); while (!v) v = Math.random(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
function _gamma(k) {                                   // Marsaglia–Tsang
  if (k < 1) return _gamma(k + 1) * Math.pow(Math.random(), 1 / k);
  const d = k - 1 / 3, c = 1 / Math.sqrt(9 * d);
  for (;;) {
    let x, v;
    do { x = _gauss(); v = 1 + c * x; } while (v <= 0);
    v = v * v * v; const u = Math.random();
    if (u < 1 - 0.0331 * x * x * x * x) return d * v;
    if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
  }
}
function _betaSample(a, b) { const x = _gamma(Math.max(a, 1e-6)), y = _gamma(Math.max(b, 1e-6)); return (x + y) > 0 ? x / (x + y) : PRIOR_CTR; }

function expectedValue(ad, ctx) {
  const price = (+ad.cpm || 20);
  const perf  = ad.perf || {};
  let variant = 'default';
  if (ad.use_variants && ad.copy_variants) {
    for (const t of VARIANT_PRIORITY) { if (ctx.has(t) && ad.copy_variants[t]) { variant = t; break; } }
  }
  const stats = (variant !== 'default' && perf.variants && perf.variants[variant])
    ? perf.variants[variant] : { imp: perf.imp || 0, clk: perf.clk || 0 };
  const imp = Math.max(0, stats.imp || 0), clk = Math.max(0, Math.min(imp, stats.clk || 0));
  const pctr = _betaSample(PRIOR_CTR * PRIOR_STRENGTH + clk, (1 - PRIOR_CTR) * PRIOR_STRENGTH + (imp - clk));
  let ev = price * (1 + CLICK_VALUE_MULT * pctr);
  const tags = new Set(ad.tags || []);
  if (tags.size && ctx.size) { for (const t of ctx) { if (tags.has(t)) { ev *= BOOST; break; } } }
  return Math.max(ev, 1e-6);
}

function selectOptimal(ads, ctx) {
  ctx = ctx || new Set();
  const scored = ads.map(a => [expectedValue(a, ctx), a]);
  const total  = scored.reduce((s, [v]) => s + v, 0);
  if (total <= 0) return ads[ads.length - 1];
  let r = Math.random() * total;
  for (const [v, a] of scored) { r -= v; if (r <= 0) return a; }
  return scored[scored.length - 1][1];
}

function detectContext() {
  const ws = vscode.workspace.workspaceFolders;
  if (!ws || ws.length === 0) return new Set();
  const root = ws[0].uri.fsPath;
  const tags = new Set();
  const checks = {
    typescript:  ['tsconfig.json', 'tsconfig.base.json'],
    python:      ['requirements.txt', 'pyproject.toml', 'setup.py', 'Pipfile'],
    rust:        ['Cargo.toml'],
    go:          ['go.mod'],
    javascript:  ['package.json', '.eslintrc.js'],
    docker:      ['Dockerfile', 'docker-compose.yml'],
    infra:       ['terraform.tf', 'main.tf', 'Pulumi.yaml', 'cdk.json'],
  };
  for (const [tag, files] of Object.entries(checks)) {
    if (files.some(f => fs.existsSync(path.join(root, f)))) tags.add(tag);
  }
  return tags;
}

function selectCopy(ad, contextTags) {
  if (!ad.use_variants || !ad.copy_variants) return ad.text;
  const priority = ['typescript', 'rust', 'go', 'python', 'javascript', 'docker', 'infra'];
  for (const tag of priority) {
    if (contextTags.has(tag) && ad.copy_variants[tag]) return ad.copy_variants[tag];
  }
  return ad.copy_variants['default'] || ad.text;
}

// ── Analytics ────────────────────────────────────────────────────────────────

function shareLevel() {
  for (const f of [CLAUDE_CFG, VSCODE_CFG]) {
    try {
      const c = JSON.parse(fs.readFileSync(f, 'utf8'));
      if (typeof c.share_level === 'number') return c.share_level;
      if (c.optin_enabled) return 1;
    } catch {}
  }
  return 0;
}

function logImpression(adId, adText, userId, variant = 'default') {
  // Route through track-event — earnings are computed server-side.
  supabasePost('/functions/v1/track-event', {
    ad_id: adId, ad_text: adText, event: 'impression',
    surface: 'vscode_statusbar', user_id: userId, variant,
    share_level: shareLevel(),
  }).catch(() => {});
}

function logClick(adId, userId) {
  supabasePost('/functions/v1/track-event', {
    ad_id: adId, ad_text: '', event: 'click',
    surface: 'vscode_click', user_id: userId,
    share_level: shareLevel(),
  }).catch(() => {});
}

// ── Earnings ─────────────────────────────────────────────────────────────────

async function fetchEarnings(userId) {
  try {
    const url  = `${SUPABASE_URL}/rest/v1/events?user_id=eq.${userId}&event=eq.impression&select=earnings_millicents`;
    const raw  = await httpsGet(url + `&apikey=${SUPABASE_KEY}`);  // not ideal but works for anon
    const rows = JSON.parse(raw);
    const mc   = rows.reduce((s, r) => s + (r.earnings_millicents || 0), 0);
    return mc / 100_000; // dollars
  } catch {
    return 0;
  }
}

// ── Extension ────────────────────────────────────────────────────────────────

/** @param {vscode.ExtensionContext} context */
async function activate(context) {
  const { userId, referralCode } = getOrCreateUser();

  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 500);
  statusBar.command = 'claude-code-ads.openAd';
  statusBar.tooltip = 'Click to visit · Claude Code Ads';
  context.subscriptions.push(statusBar);

  let currentAd   = null;
  let currentText = '';
  let currentVariant = 'default';

  // Viewability gate: only count an impression when the developer is actually
  // present, not merely when the window holds OS focus. We treat editing,
  // navigating, or refocusing the window as activity; after IDLE_MS of none, the
  // status-bar ad is still shown but stops accruing impressions — this keeps an
  // unattended-but-focused editor from minting endless impressions.
  let lastActivity = Date.now();
  const markActive = () => { lastActivity = Date.now(); };
  context.subscriptions.push(
    vscode.window.onDidChangeTextEditorSelection(markActive),
    vscode.workspace.onDidChangeTextDocument(markActive),
    vscode.window.onDidChangeActiveTextEditor(markActive),
    vscode.window.onDidChangeWindowState(s => { if (s.focused) markActive(); }),
  );

  const openAdCmd = vscode.commands.registerCommand('claude-code-ads.openAd', () => {
    if (currentAd) {
      vscode.env.openExternal(vscode.Uri.parse(currentAd.url));
      logClick(currentAd.id, userId);
    }
  });

  const showEarningsCmd = vscode.commands.registerCommand('claude-code-ads.showEarnings', async () => {
    const dollars = await fetchEarnings(userId);
    const invite = referralCode
      ? `https://bggprogramming.github.io/mango/invite.html?ref=${referralCode}`
      : 'https://bggprogramming.github.io/mango/';
    vscode.window.showInformationMessage(
      `Claude Code Ads: $${dollars.toFixed(2)} earned. Invite a friend — you both get $10.`,
      'Copy invite link', 'Open portal'
    ).then(sel => {
      if (sel === 'Copy invite link') vscode.env.clipboard.writeText(invite);
      else if (sel === 'Open portal') vscode.env.openExternal(vscode.Uri.parse('https://bggprogramming.github.io/mango/portal.html'));
    });
  });

  context.subscriptions.push(openAdCmd, showEarningsCmd);

  async function updateAd() {
    const ads = await loadAds();
    if (!ads.length) return;

    const contextTags = detectContext();
    currentAd         = selectOptimal(ads, contextTags);   // eCPM (bid×pCTR) ranking
    currentText       = selectCopy(currentAd, contextTags);
    currentVariant    = (currentAd.use_variants && currentAd.copy_variants)
      ? (['typescript','rust','go','python','javascript','docker','infra']
          .find(t => contextTags.has(t) && currentAd.copy_variants[t]) || 'default')
      : 'default';

    // Truncate to fit status bar
    const display = currentText.length > 70 ? currentText.slice(0, 69) + '…' : currentText;
    statusBar.text  = `${display} ↗`;
    statusBar.show();

    // Count an impression only when the window is on screen AND the developer
    // has been active recently. VS Code's API exposes focus (not occlusion), so
    // focus + recent activity is our viewability proxy; this avoids inflating
    // impressions (and the advertiser-facing CTR) on an idle, walked-away editor.
    if (vscode.window.state.focused && (Date.now() - lastActivity) < IDLE_MS) {
      logImpression(currentAd.id, currentText, userId, currentVariant);
    }
  }

  await updateAd();
  const timer = setInterval(updateAd, REFRESH_MS);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });
}

function deactivate() {}

module.exports = { activate, deactivate };
