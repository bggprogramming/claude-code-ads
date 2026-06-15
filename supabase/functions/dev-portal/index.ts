import { createClient } from 'jsr:@supabase/supabase-js@2'

// Developer portal data, keyed by referral code: lifetime earnings (impressions +
// clicks), payout progress, impressions by surface, clicks, referrals + bonuses.

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
}
const PAYOUT_MC = 1_000_000
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' } })

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })
  const code = new URL(req.url).searchParams.get('code')?.trim().toLowerCase()
  if (!code) return json(400, { error: 'code required' })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })

  const { data: user } = await supabase
    .from('users').select('id, referral_code, referred_by, milestone_hit, created_at')
    .eq('referral_code', code).maybeSingle()
  if (!user) return json(404, { error: 'not found', code })

  const { data: evs } = await supabase
    .from('events').select('event, surface, earnings_millicents').eq('user_id', user.id)

  const bySurface: Record<string, { impressions: number; mc: number }> = {}
  let totalMc = 0, totalImp = 0, totalClicks = 0, clickMc = 0
  for (const e of evs ?? []) {
    const amt = e.earnings_millicents ?? 0
    totalMc += amt
    if (e.event === 'click') { totalClicks++; clickMc += amt; continue }
    totalImp++
    const s = e.surface || 'unknown'
    bySurface[s] ??= { impressions: 0, mc: 0 }
    bySurface[s].impressions++; bySurface[s].mc += amt
  }

  const { data: refs } = await supabase
    .from('users').select('referral_code, milestone_hit, created_at')
    .eq('referred_by', code).order('created_at', { ascending: false })

  const { data: bonuses } = await supabase
    .from('referral_bonuses').select('amount_millicents, status, recipient')
    .eq('referrer_code', code)
  let pendingMc = 0, paidMc = 0
  for (const b of bonuses ?? []) {
    if (b.recipient !== 'referrer') continue
    if (b.status === 'paid') paidMc += b.amount_millicents ?? 0
    else pendingMc += b.amount_millicents ?? 0
  }

  return json(200, {
    referral_code: user.referral_code,
    referred_by: user.referred_by,
    milestone_hit: user.milestone_hit,
    created_at: user.created_at,
    total_millicents: totalMc,
    total_dollars: totalMc / 100_000,
    total_impressions: totalImp,
    total_clicks: totalClicks,
    click_dollars: clickMc / 100_000,
    payout_target_dollars: PAYOUT_MC / 100_000,
    payout_pct: Math.min(100, Math.round((totalMc / PAYOUT_MC) * 100)),
    by_surface: Object.entries(bySurface).map(([surface, v]) => ({ surface, impressions: v.impressions, dollars: v.mc / 100_000 })).sort((a, b) => b.impressions - a.impressions),
    referrals: (refs ?? []).map((r: any) => ({ code: r.referral_code, milestone_hit: r.milestone_hit, joined: r.created_at })),
    referral_count: (refs ?? []).length,
    bonus_pending_dollars: pendingMc / 100_000,
    bonus_paid_dollars: paidMc / 100_000,
  })
})
