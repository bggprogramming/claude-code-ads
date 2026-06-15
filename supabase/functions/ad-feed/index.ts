import { createClient } from 'jsr:@supabase/supabase-js@2'

// Authoritative ad feed: built-in house ads + active PAID advertiser campaigns,
// ordered so higher bids serve more often (rotation weight ∝ bid). Returns a
// sha256 over the canonical payload so clients can verify integrity.

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
}
const STORAGE_PUBLIC = '/storage/v1/object/public/'

const HOUSE = [
  {
    id: 'ad_cursor',
    text: '✦ Cursor — Accept the next line of code with Tab. Ships in half the time. cursor.com',
    url: 'https://cursor.com', weight: 2, cpm: 25, logo_url: null,
    tags: ['javascript','typescript','python','rust','go'], use_variants: true,
    copy_variants: {
      default: '✦ Cursor — Accept the next line of code with Tab. Ships in half the time. cursor.com',
      typescript: '✦ Cursor — TypeScript autocomplete that actually understands your types. cursor.com',
      python: '✦ Cursor — Writes your Python tests before you do. cursor.com',
      rust: '✦ Cursor — Borrow checker errors explained inline. cursor.com',
      go: '✦ Cursor — Go autocomplete without the boilerplate. cursor.com',
      javascript: '✦ Cursor — JavaScript that autocompletes exactly how you think. cursor.com',
    },
    completion_text: '──── Cursor — AI pair programmer that actually ships ↗ ────',
  },
  {
    id: 'ad_warp',
    text: '⚡ Warp — Search 10,000 past commands in under a second. Never retype again. warp.dev',
    url: 'https://warp.dev', weight: 2, cpm: 22, logo_url: null,
    tags: ['docker','infra','javascript','python'], use_variants: true,
    copy_variants: {
      default: '⚡ Warp — Search 10,000 past commands in under a second. Never retype again. warp.dev',
      docker: '⚡ Warp — Your Docker logs, grep-able in milliseconds. warp.dev',
      infra: '⚡ Warp — Run and share complex infra commands as reusable workflows. warp.dev',
      python: '⚡ Warp — pip install, venv activate, run — all remembered. warp.dev',
      javascript: '⚡ Warp — npm scripts that actually make sense. Searchable history. warp.dev',
    },
    completion_text: '──── Warp — the terminal built for developers ↗ ────',
  },
  {
    id: 'ad_linear',
    text: '◆ Linear — Close issues 3× faster than Jira. Free for small teams. linear.app',
    url: 'https://linear.app', weight: 2, cpm: 20, logo_url: null, tags: [], use_variants: false, copy_variants: {},
    completion_text: '──── Linear — issue tracking built for speed ↗ ────',
  },
]

async function sha256Hex(s: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  const baseUrl = Deno.env.get('SUPABASE_URL') ?? ''
  const supabase = createClient(baseUrl, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '', { auth: { persistSession: false } })

  const { data: camps } = await supabase
    .from('advertisers')
    .select('ad_id, company, ad_text, url, logo_path, logo_url, bid_per_block_cents, blocks, impressions_delivered, use_variants, copy_variants')
    .eq('status', 'active').eq('paid', true)

  const live = (camps ?? [])
    .filter((c: any) => c.impressions_delivered < c.blocks * 1000)
    .sort((a: any, b: any) => b.bid_per_block_cents - a.bid_per_block_cents)

  const advAds = live.map((c: any) => ({
    id: c.ad_id,
    text: c.ad_text,
    url: c.url,
    weight: Math.max(1, Math.round(c.bid_per_block_cents / 10)),
    cpm: c.bid_per_block_cents / 100,
    tags: [],
    use_variants: !!c.use_variants,
    copy_variants: c.copy_variants || {},
    logo_url: c.logo_path ? `${baseUrl}${STORAGE_PUBLIC}${c.logo_path}` : (c.logo_url || null),
    completion_text: `──── ${c.company ? c.company + ' — ' : ''}${c.ad_text || c.url} ↗ ────`,
  }))

  const ads = [...advAds, ...HOUSE]

  // Per-ad performance (last 30d): impressions/clicks globally and per variant.
  // Clients rank by expected value (eCPM = price × predicted-CTR) using these
  // aggregate counts; the context that picks a variant never leaves the device.
  const ids = ads.map((a: any) => a.id)
  if (ids.length) {
    const since = new Date(Date.now() - 30 * 86_400_000).toISOString()
    const { data: evs } = await supabase
      .from('events').select('ad_id, event, variant')
      .in('ad_id', ids).gte('ts', since).limit(200_000)
    const perf: Record<string, any> = {}
    for (const e of evs ?? []) {
      const p = (perf[e.ad_id] ??= { imp: 0, clk: 0, variants: {} })
      const v = (p.variants[e.variant || 'default'] ??= { imp: 0, clk: 0 })
      if (e.event === 'click') { p.clk++; v.clk++ } else { p.imp++; v.imp++ }
    }
    for (const a of ads) (a as any).perf = perf[a.id] || { imp: 0, clk: 0, variants: {} }
  }

  const hash = await sha256Hex(JSON.stringify(ads))

  return new Response(JSON.stringify({ ads, hash }), {
    headers: { ...corsHeaders, 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' },
  })
})
