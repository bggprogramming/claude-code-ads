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
const FEED_URL      = 'https://raw.githubusercontent.com/bggprogramming/claude-code-ads/main/ads.json';
const REFRESH_MS    = 30_000;
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
  statusBar.tooltip = 'Sponsored — click to visit · Claude Code Ads';
  context.subscriptions.push(statusBar);

  let currentAd   = null;
  let currentText = '';
  let currentVariant = 'default';

  const openAdCmd = vscode.commands.registerCommand('claude-code-ads.openAd', () => {
    if (currentAd) {
      vscode.env.openExternal(vscode.Uri.parse(currentAd.url));
      logClick(currentAd.id, userId);
    }
  });

  const showEarningsCmd = vscode.commands.registerCommand('claude-code-ads.showEarnings', async () => {
    const dollars = await fetchEarnings(userId);
    const invite = referralCode
      ? `https://bggprogramming.github.io/claude-code-ads/invite.html?ref=${referralCode}`
      : 'https://bggprogramming.github.io/claude-code-ads/';
    vscode.window.showInformationMessage(
      `Claude Code Ads: $${dollars.toFixed(2)} earned. Invite a friend — you both get $10.`,
      'Copy invite link', 'Open portal'
    ).then(sel => {
      if (sel === 'Copy invite link') vscode.env.clipboard.writeText(invite);
      else if (sel === 'Open portal') vscode.env.openExternal(vscode.Uri.parse('https://bggprogramming.github.io/claude-code-ads/portal.html'));
    });
  });

  context.subscriptions.push(openAdCmd, showEarningsCmd);

  async function updateAd() {
    const ads = await loadAds();
    if (!ads.length) return;

    const contextTags = detectContext();
    currentAd         = weightedSample(ads);
    currentText       = selectCopy(currentAd, contextTags);
    currentVariant    = (currentAd.use_variants && currentAd.copy_variants)
      ? (['typescript','rust','go','python','javascript','docker','infra']
          .find(t => contextTags.has(t) && currentAd.copy_variants[t]) || 'default')
      : 'default';

    // Truncate to fit status bar
    const display = currentText.length > 70 ? currentText.slice(0, 69) + '…' : currentText;
    statusBar.text  = `$(megaphone) ${display}`;
    statusBar.show();

    // Count an impression only when the window is actually on screen. VS Code's
    // API exposes focus (not occlusion), so we use focus as the visibility proxy.
    if (vscode.window.state.focused) {
      logImpression(currentAd.id, currentText, userId, currentVariant);
    }
  }

  await updateAd();
  const timer = setInterval(updateAd, REFRESH_MS);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });
}

function deactivate() {}

module.exports = { activate, deactivate };
