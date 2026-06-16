import { createClient } from 'jsr:@supabase/supabase-js@2'

// Developer portal data, keyed by referral code: lifetime earnings (impressions +
// clicks), payout progress, impressions by surface, clicks, referrals + bonuses.
//
// Multi-device: a developer can link several device accounts into one (see the
// link-device function / users.linked_to). The portal resolves the signed-in
// code to its *primary* account and aggregates events/payouts across the primary
// and every device linked to it — so earnings show as one unified total no
// matter which device's code you sign in with.

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

  const { data: signedIn } = await supabase
    .from('users').select('id, referral_code, referred_by, milestone_hit, created_at, stripe_account_id, payouts_enabled, linked_to')
    .eq('referral_code', code).maybeSingle()
  if (!signedIn) return json(404, { error: 'not found', code })

  // Resolve to the primary account (the signed-in code may itself be a linked device).
  const primaryId = signedIn.linked_to ?? signedIn.id
  const { data: primary } = await supabase
    .from('users').select('id, referral_code, referred_by, milestone_hit, created_at, stripe_account_id, payouts_enabled')
    .eq('id', primaryId).maybeSingle()
  const acct = primary ?? signedIn

  // All device accounts in this household: the primary + everything linked to it.
  const { data: devices } = await supabase
    .from('users').select('id, referral_code')
    .or(`id.eq.${acct.id},linked_to.eq.${acct.id}`)
  const deviceIds   = (devices ?? []).map(d => d.id)
  const deviceCodes = (devices ?? []).map(d => d.referral_code).filter(Boolean)
  const ids   = deviceIds.length   ? deviceIds   : [acct.id]
  const codes = deviceCodes.length ? deviceCodes : [acct.referral_code]

  // Earnings across every linked device.
  const { data: evs } = await supabase
    .from('events').select('event, surface, earnings_millicents').in('user_id', ids)

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

  // Payout history + available balance, across linked devices.
  const { data: pays } = await supabase
    .from('payouts').select('amount_millicents, status, created_at, paid_at')
    .in('user_id', ids).order('created_at', { ascending: false })
  let paidOutMc = 0, pendingPayoutMc = 0
  for (const p of pays ?? []) {
    if (p.status === 'paid') paidOutMc += p.amount_millicents ?? 0
    else if (p.status === 'pending') pendingPayoutMc += p.amount_millicents ?? 0
  }
  const MIN_PAYOUT_MC = 1_000_000   // $10 minimum cash-out
  const availableMc   = Math.max(0, totalMc - paidOutMc - pendingPayoutMc)

  // Referrals + bonuses across every code this household owns.
  const { data: refs } = await supabase
    .from('users').select('referral_code, milestone_hit, created_at')
    .in('referred_by', codes).order('created_at', { ascending: false })

  const { data: bonuses } = await supabase
    .from('referral_bonuses').select('amount_millicents, status, recipient')
    .in('referrer_code', codes)
  let pendingMc = 0, paidMc = 0
  for (const b of bonuses ?? []) {
    if (b.recipient !== 'referrer') continue
    if (b.status === 'paid') paidMc += b.amount_millicents ?? 0
    else pendingMc += b.amount_millicents ?? 0
  }

  return json(200, {
    referral_code: acct.referral_code,          // the canonical code to share
    referred_by: acct.referred_by,
    milestone_hit: acct.milestone_hit || totalMc >= PAYOUT_MC / 2,
    created_at: acct.created_at,
    linked_devices: ids.length,                  // how many devices roll up here
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
    // Cash-out
    payouts_enabled: !!acct.payouts_enabled,
    connected: !!acct.stripe_account_id,
    available_dollars: availableMc / 100_000,
    paid_out_dollars: paidOutMc / 100_000,
    pending_payout_dollars: pendingPayoutMc / 100_000,
    min_payout_dollars: MIN_PAYOUT_MC / 100_000,
    can_cash_out: availableMc >= MIN_PAYOUT_MC,
    payouts: (pays ?? []).map((p: any) => ({
      dollars: (p.amount_millicents ?? 0) / 100_000, status: p.status,
      created: p.created_at, paid: p.paid_at,
    })),
  })
})
