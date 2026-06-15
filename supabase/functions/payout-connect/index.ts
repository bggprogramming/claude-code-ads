import { createClient } from 'jsr:@supabase/supabase-js@2'

// Stripe Connect onboarding for developer payouts. POST { code }.
// Creates (once) an Express connected account for the developer and returns a
// hosted onboarding link. Build-ready: if STRIPE_SECRET_KEY is unset it returns
// { configured: false } so the portal can show "payouts coming soon" gracefully.

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const SITE_BASE = Deno.env.get('SITE_BASE') ?? 'https://bggprogramming.github.io/claude-code-ads'
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json' } })

async function stripe(path: string, key: string, form: URLSearchParams) {
  const r = await fetch(`https://api.stripe.com/v1/${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form.toString(),
  })
  return { ok: r.ok, body: await r.json() }
}

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
    .from('users').select('id, referral_code, stripe_account_id, payouts_enabled')
    .eq('referral_code', code).maybeSingle()
  if (!user) return json(404, { error: 'not found' })

  const key = Deno.env.get('STRIPE_SECRET_KEY')
  if (!key) return json(200, { configured: false, message: 'Payouts are not enabled yet — check back soon.' })

  // Create the connected account once.
  let acct = user.stripe_account_id
  if (!acct) {
    const f = new URLSearchParams()
    f.set('type', 'express')
    f.set('capabilities[transfers][requested]', 'true')
    f.set('business_type', 'individual')
    f.set('metadata[user_id]', user.id)
    const r = await stripe('accounts', key, f)
    if (!r.ok) return json(502, { error: 'stripe error', detail: r.body })
    acct = r.body.id
    await supabase.from('users').update({ stripe_account_id: acct }).eq('id', user.id)
  }

  const link = new URLSearchParams()
  link.set('account', acct)
  link.set('refresh_url', `${SITE_BASE}/portal.html?code=${user.referral_code}&connect=retry`)
  link.set('return_url',  `${SITE_BASE}/portal.html?code=${user.referral_code}&connect=done`)
  link.set('type', 'account_onboarding')
  const r = await stripe('account_links', key, link)
  if (!r.ok) return json(502, { error: 'stripe error', detail: r.body })
  return json(200, { configured: true, url: r.body.url })
})
