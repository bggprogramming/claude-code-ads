import { createClient } from 'jsr:@supabase/supabase-js@2'

// Server-authoritative event tracking. Clients cannot set their own earnings.
// Impressions: developer earns 50% of the ad's per-impression price.
// Clicks: billed at 50× the impression rate (developer earns 50% of that).
// Only path allowed to write `events` (anon INSERT is revoked by RLS).

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}

const MILESTONE_MC      = 500_000
const REFERRAL_BONUS_MC = 1_000_000
const DEV_SHARE         = 0.5
const CLICK_MULTIPLIER  = 50          // clicks bill at 50× the impression rate

const BUILTIN_CPM: Record<string, number> = { ad_cursor: 25, ad_warp: 22, ad_linear: 20 }
const DEFAULT_CPM = 20

const ALLOWED_SURFACES = new Set([
  'statusline', 'spinner', 'completion', 'vscode_statusbar', 'vscode_click', 'click', 'unknown',
])

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })

// House-ad rate card: dev earning per impression = rate(surface) × CPM.
function houseMc(cpm: number, surface: string): number {
  if (surface === 'statusline' || surface === 'vscode_statusbar') return cpm * 100
  if (surface === 'completion') return cpm * 200
  return cpm * 50
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  let body: any = {}
  try { body = await req.json() } catch { return json(400, { error: 'invalid json' }) }

  const adId    = String(body.ad_id ?? '').trim()
  const adText  = String(body.ad_text ?? '')
  const event   = String(body.event ?? 'impression')
  let   surface = String(body.surface ?? 'unknown')
  const userId  = body.user_id ? String(body.user_id) : null
  const variant = String(body.variant ?? 'default')

  if (!adId)                          return json(400, { error: 'ad_id required' })
  if (event !== 'impression' && event !== 'click')
                                      return json(400, { error: 'event must be impression|click' })
  if (!ALLOWED_SURFACES.has(surface)) surface = 'unknown'

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')              ?? '',
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } }
  )

  // Resolve the ad: built-in house ad, or an auction advertiser campaign.
  let adv: any = null
  if (BUILTIN_CPM[adId] == null) {
    const { data } = await supabase
      .from('advertisers')
      .select('id, bid_per_block_cents, blocks, impressions_delivered, status')
      .eq('ad_id', adId).maybeSingle()
    adv = data
  }

  // Developer earnings recorded on the event.
  const baseImpressionMc = adv
    ? Math.round(adv.bid_per_block_cents * DEV_SHARE)
    : houseMc(BUILTIN_CPM[adId] ?? DEFAULT_CPM, surface === 'click' ? 'statusline' : surface)
  const mc = event === 'click' ? baseImpressionMc * CLICK_MULTIPLIER
           : (adv ? Math.round(adv.bid_per_block_cents * DEV_SHARE) : houseMc(BUILTIN_CPM[adId] ?? DEFAULT_CPM, surface))

  const { error: insErr } = await supabase.from('events').insert({
    ad_id: adId, ad_text: adText, event, surface,
    user_id: userId, variant, earnings_millicents: mc,
  })
  if (insErr) return json(500, { error: 'insert failed', detail: insErr.message })

  // Auction delivery accounting (impressions only; clicks don't consume inventory).
  if (adv && event === 'impression') {
    const delivered = (adv.impressions_delivered ?? 0) + 1
    const target    = (adv.blocks ?? 1) * 1000
    const patch: any = { impressions_delivered: delivered }
    if (delivered >= target) patch.status = 'exhausted'
    await supabase.from('advertisers').update(patch).eq('id', adv.id)
  }

  // Developer milestone + referral bonus. Total earnings = ALL events (incl. clicks).
  let milestoneHit = false
  let totalMc: number | null = null
  if (userId) {
    const { data: rows } = await supabase
      .from('events').select('earnings_millicents').eq('user_id', userId)
    totalMc = (rows ?? []).reduce((s: number, r: any) => s + (r.earnings_millicents ?? 0), 0)

    if (totalMc >= MILESTONE_MC) {
      const { data: u } = await supabase
        .from('users').select('referral_code, referred_by, milestone_hit')
        .eq('id', userId).maybeSingle()
      if (u && !u.milestone_hit) {
        if (u.referred_by) {
          await supabase.from('referral_bonuses').upsert([
            { referrer_code: u.referred_by, referred_code: u.referral_code, amount_millicents: REFERRAL_BONUS_MC, recipient: 'referrer' },
            { referrer_code: u.referred_by, referred_code: u.referral_code, amount_millicents: REFERRAL_BONUS_MC, recipient: 'referred' },
          ], { onConflict: 'referrer_code,referred_code,recipient', ignoreDuplicates: true })
        }
        await supabase.from('users').update({ milestone_hit: true }).eq('id', userId)
        milestoneHit = true
      }
    }
  }

  return json(200, { ok: true, earnings_millicents: mc, total_millicents: totalMc, milestone_hit: milestoneHit })
})
