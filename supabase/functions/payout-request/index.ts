import { createClient } from 'jsr:@supabase/supabase-js@2'

// Developer cash-out. POST { code }. Pays out the available balance (lifetime
// earnings − already paid/pending payouts), min $10. Build-ready:
//   • STRIPE_SECRET_KEY set + account onboarded → Stripe transfer, status 'paid'
//   • otherwise → records a 'pending' payout row (settled manually / when live)

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const MIN_PAYOUT_MC = 1_000_000   // $10
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json' } })

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  let body: any = {}
  try { body = await req.json() } catch { return json(400, { error: 'invalid json' }) }
  const code = String(body.code ?? '').trim().toLowerCase()
  if (!code) return json(400, { error: 'code required' })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })

  const { data: user } = await supabase
    .from('users').select('id, stripe_account_id, payouts_enabled')
    .eq('referral_code', code).maybeSingle()
  if (!user) return json(404, { error: 'not found' })

  // Available = lifetime earnings − already paid/pending payouts (server-computed).
  const { data: evs } = await supabase
    .from('events').select('earnings_millicents').eq('user_id', user.id)
  const totalMc = (evs ?? []).reduce((s: number, r: any) => s + (r.earnings_millicents ?? 0), 0)

  const { data: pays } = await supabase
    .from('payouts').select('amount_millicents, status').eq('user_id', user.id)
  const usedMc = (pays ?? []).reduce((s: number, p: any) =>
    (p.status === 'paid' || p.status === 'pending') ? s + (p.amount_millicents ?? 0) : s, 0)

  const availableMc = Math.max(0, totalMc - usedMc)
  if (availableMc < MIN_PAYOUT_MC) {
    return json(400, { error: 'below minimum', available_dollars: availableMc / 100_000, min_dollars: MIN_PAYOUT_MC / 100_000 })
  }

  const key = Deno.env.get('STRIPE_SECRET_KEY')

  // No Stripe / not onboarded → record a pending payout for manual settlement.
  if (!key || !user.stripe_account_id) {
    const { error } = await supabase.from('payouts').insert({
      user_id: user.id, amount_millicents: availableMc, status: 'pending',
      note: key ? 'awaiting account onboarding' : 'awaiting payout processor',
    })
    if (error) return json(500, { error: 'could not record payout', detail: error.message })
    return json(200, { status: 'pending', amount_dollars: availableMc / 100_000,
      message: 'Cash-out requested. It will be sent once payouts are enabled on your account.' })
  }

  // Live: Stripe transfer to the connected account.
  const f = new URLSearchParams()
  f.set('amount', String(Math.round(availableMc / 1000)))   // millicents → cents
  f.set('currency', 'usd')
  f.set('destination', user.stripe_account_id)
  f.set('metadata[user_id]', user.id)
  const r = await fetch('https://api.stripe.com/v1/transfers', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: f.toString(),
  })
  const tr = await r.json()
  if (!r.ok) {
    await supabase.from('payouts').insert({
      user_id: user.id, amount_millicents: availableMc, status: 'failed',
      note: (tr?.error?.message ?? 'stripe error').slice(0, 200),
    })
    return json(502, { error: 'stripe transfer failed', detail: tr })
  }
  await supabase.from('payouts').insert({
    user_id: user.id, amount_millicents: availableMc, status: 'paid',
    stripe_transfer_id: tr.id, paid_at: new Date().toISOString(),
  })
  return json(200, { status: 'paid', amount_dollars: availableMc / 100_000, transfer_id: tr.id })
})
