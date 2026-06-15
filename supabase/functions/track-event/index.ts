import { createClient } from 'jsr:@supabase/supabase-js@2'

// Server-authoritative event tracking. Clients cannot set their own earnings.
// Impressions: developer earns 50% of the ad's per-impression price.
// Clicks: billed at 50× the impression rate (developer earns 50% of that).
// Earnings-sharing tier multiplies the developer's share (more context shared
// → better targeting → advertisers bid more → the developer earns more).
// Only path allowed to write `events` (anon INSERT is revoked by RLS).
//
// Anti-fraud (clients pick ad_id/event/surface, so volume/shape is untrusted):
//   • per-user burst rate-limit  (drop earnings beyond RATE_MAX / RATE_WINDOW)
//   • per-user daily earnings cap (clamp so one account can't mint unlimited $)
//   • click validation           (a paid click needs a recent matching impression)
// These raise the bar; the real backstop is KYC at payout (Stripe Connect).

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}

const MILESTONE_MC      = 500_000
const REFERRAL_BONUS_MC = 1_000_000
const DEV_SHARE         = 0.5
const CLICK_MULTIPLIER  = 50
const SHARE_MULT        = [1.0, 1.3, 1.7, 2.5]   // by share_level (0..3)

const RATE_WINDOW_MS    = 10_000      // burst window
const RATE_MAX          = 8           // max earning events per user per window
const DAILY_CAP_MC      = 1_000_000   // $10/day/user safety cap on earnings
const CLICK_LOOKBACK_MS = 60 * 60_000 // a click only pays 50× if a matching impression is ≤1h old

const BUILTIN_CPM: Record<string, number> = { ad_cursor: 25, ad_warp: 22, ad_linear: 20 }
const DEFAULT_CPM = 20

const ALLOWED_SURFACES = new Set([
  'statusline', 'spinner', 'completion', 'scrollback',
  'vscode_statusbar', 'vscode_click', 'click', 'unknown',
])

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })

function houseMc(cpm: number, surface: string): number {
  if (surface === 'statusline' || surface === 'vscode_statusbar' || surface === 'scrollback') return cpm * 100
  if (surface === 'completion') return cpm * 200
  return cpm * 50
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  let body: any = {}
  try { body = await req.json() } catch { return json(400, { error: 'invalid json' }) }

  const adId    = String(body.ad_id ?? '').trim()
  const adText  = String(body.ad_text ?? '').slice(0, 300)
  const event   = String(body.event ?? 'impression')
  let   surface = String(body.surface ?? 'unknown')
  const userId  = body.user_id ? String(body.user_id).slice(0, 64) : null
  const variant = String(body.variant ?? 'default').slice(0, 40)
  const lvl     = Math.max(0, Math.min(3, parseInt(body.share_level ?? 0) || 0))

  if (!adId)                          return json(400, { error: 'ad_id required' })
  if (event !== 'impression' && event !== 'click')
                                      return json(400, { error: 'event must be impression|click' })
  if (!ALLOWED_SURFACES.has(surface)) surface = 'unknown'

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')              ?? '',
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } }
  )

  let adv: any = null
  if (BUILTIN_CPM[adId] == null) {
    const { data } = await supabase
      .from('advertisers')
      .select('id, bid_per_block_cents, blocks, impressions_delivered, status')
      .eq('ad_id', adId).maybeSingle()
    adv = data
  }

  // ── Anti-fraud: gather today's recent events for this user (one query) ──────
  const now        = Date.now()
  const startOfDay = new Date(); startOfDay.setUTCHours(0, 0, 0, 0)
  let recent: any[] = []
  if (userId) {
    const { data } = await supabase
      .from('events').select('ts, event, ad_id, earnings_millicents')
      .eq('user_id', userId).gte('ts', startOfDay.toISOString())
      .order('ts', { ascending: false }).limit(100_000)
    recent = data ?? []
  }

  // Burst rate-limit: too many earning events in the window → record at 0 earnings.
  const burst = recent.filter(e => now - new Date(e.ts).getTime() < RATE_WINDOW_MS).length
  const rateLimited = userId != null && burst >= RATE_MAX

  // A click only earns the 50× multiplier if a matching impression is recent.
  let payClick = event === 'click'
  if (payClick && userId) {
    const hasImp = recent.some(e =>
      e.event === 'impression' && e.ad_id === adId &&
      now - new Date(e.ts).getTime() < CLICK_LOOKBACK_MS)
    if (!hasImp) payClick = false   // treat as a normal impression-priced event
  }

  const impMc = adv
    ? Math.round(adv.bid_per_block_cents * DEV_SHARE)
    : houseMc(BUILTIN_CPM[adId] ?? DEFAULT_CPM, surface === 'click' ? 'statusline' : surface)
  let mc = payClick ? impMc * CLICK_MULTIPLIER : impMc
  mc = Math.round(mc * SHARE_MULT[lvl])

  // Daily earnings cap (clamp to remaining; never negative).
  if (userId) {
    const todayMc = recent.reduce((s, e) => s + (e.earnings_millicents ?? 0), 0)
    const remaining = Math.max(0, DAILY_CAP_MC - todayMc)
    if (rateLimited) mc = 0
    else             mc = Math.min(mc, remaining)
  }

  const { error: insErr } = await supabase.from('events').insert({
    ad_id: adId, ad_text: adText, event, surface,
    user_id: userId, variant, earnings_millicents: mc,
  })
  if (insErr) return json(500, { error: 'insert failed', detail: insErr.message })

  // Advertiser delivery accounting (impressions only; counts even if dev was capped).
  if (adv && event === 'impression') {
    const delivered = (adv.impressions_delivered ?? 0) + 1
    const target    = (adv.blocks ?? 1) * 1000
    const patch: any = { impressions_delivered: delivered }
    if (delivered >= target) patch.status = 'exhausted'
    await supabase.from('advertisers').update(patch).eq('id', adv.id)
  }

  // Milestone / referral bonus — uses full lifetime earnings.
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
        await supabase.from('funnel_events').insert({ code: u.referral_code, step: 'milestone' })
        milestoneHit = true
      }
    }
  }

  return json(200, {
    ok: true, earnings_millicents: mc, share_level: lvl,
    total_millicents: totalMc, milestone_hit: milestoneHit,
    rate_limited: rateLimited,
  })
})
