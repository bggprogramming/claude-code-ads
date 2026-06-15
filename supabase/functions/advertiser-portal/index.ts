import { createClient } from 'jsr:@supabase/supabase-js@2'

// Account-level advertiser portal. Auth = ANY of the advertiser's secret
// dashboard_keys (unguessable UUIDs). Given one key we resolve the owner email
// server-side and return EVERY campaign under that email, with per-campaign and
// account-rollup analytics. The full email is never returned (masked only).

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
}
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' } })

function maskEmail(e: string): string {
  const [u, d] = String(e || '').split('@')
  if (!d) return 'your account'
  const head = u.length <= 1 ? u : u[0]
  return `${head}${'*'.repeat(Math.max(2, u.length - 1))}@${d}`
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })
  const key = new URL(req.url).searchParams.get('key')?.trim()
  if (!key) return json(400, { error: 'key required' })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })

  // Resolve the owner email from the provided dashboard_key.
  const { data: owner } = await supabase
    .from('advertisers').select('email').eq('dashboard_key', key).maybeSingle()
  if (!owner) return json(404, { error: 'campaign not found for that key' })
  const email = owner.email

  // All campaigns for this email.
  const { data: camps } = await supabase
    .from('advertisers')
    .select('ad_id, dashboard_key, company, ad_text, url, status, paid, logo_path, bid_per_block_cents, blocks, impressions_delivered, created_at')
    .eq('email', email).order('created_at', { ascending: false })

  const adIds = (camps ?? []).map((c: any) => c.ad_id)

  // Per-campaign event aggregation.
  const byAd: Record<string, { impressions: number; clicks: number }> = {}
  if (adIds.length) {
    const { data: evs } = await supabase
      .from('events').select('ad_id, event').in('ad_id', adIds).limit(100000)
    for (const e of evs ?? []) {
      byAd[e.ad_id] ??= { impressions: 0, clicks: 0 }
      if (e.event === 'click') byAd[e.ad_id].clicks++
      else byAd[e.ad_id].impressions++
    }
  }

  const spendOf = (c: any, imp: number, clk: number) =>
    (c.bid_per_block_cents / 100) * (imp + 50 * clk) / 1000

  let tImp = 0, tClk = 0, tSpend = 0, active = 0
  const campaigns = (camps ?? []).map((c: any) => {
    const a = byAd[c.ad_id] || { impressions: 0, clicks: 0 }
    const spend = spendOf(c, a.impressions, a.clicks)
    tImp += a.impressions; tClk += a.clicks; tSpend += spend
    if (c.status === 'active' && c.paid) active++
    return {
      ad_id: c.ad_id, dashboard_key: c.dashboard_key, company: c.company, ad_text: c.ad_text,
      url: c.url, status: c.status, paid: c.paid, logo_path: c.logo_path,
      bid_per_block_cents: c.bid_per_block_cents, blocks: c.blocks,
      impressions_delivered: c.impressions_delivered, created_at: c.created_at,
      impressions: a.impressions, clicks: a.clicks,
      ctr: a.impressions ? (a.clicks / a.impressions * 100) : 0,
      spend_dollars: spend,
    }
  })

  return json(200, {
    email_masked: maskEmail(email),
    campaign_count: campaigns.length,
    active_count: active,
    totals: {
      impressions: tImp, clicks: tClk,
      ctr: tImp ? (tClk / tImp * 100) : 0,
      spend_dollars: tSpend,
    },
    campaigns,
  })
})
