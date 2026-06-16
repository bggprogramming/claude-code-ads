import { createClient } from 'jsr:@supabase/supabase-js@2'

// Builds a Stripe Checkout session for an auction campaign (bid_per_block × blocks).
// If STRIPE_SECRET_KEY is set → returns a Stripe checkout {url} and the campaign stays
// 'pending' until the stripe-webhook marks it paid/active.
// If NOT set → no-payment mode: the campaign is activated immediately so the
// marketplace is usable for testing / pre-payment launch. Wiring the Stripe key
// flips this back to payment-gated automatically.

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const SITE_BASE = Deno.env.get('SITE_BASE') ?? 'https://bggprogramming.github.io/mango'
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  let body: any = {}
  try { body = await req.json() } catch { return json(400, { error: 'invalid json' }) }
  const adId = String(body.ad_id ?? '').trim()
  if (!adId) return json(400, { error: 'ad_id required' })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } }
  )
  const { data: adv } = await supabase
    .from('advertisers')
    .select('ad_id, email, ad_text, company, bid_per_block_cents, blocks, dashboard_key, paid')
    .eq('ad_id', adId).maybeSingle()
  if (!adv) return json(404, { error: 'campaign not found' })
  if (adv.paid) return json(200, { already_paid: true, dashboard_key: adv.dashboard_key })

  const amount = adv.bid_per_block_cents * adv.blocks
  const stripeKey = Deno.env.get('STRIPE_SECRET_KEY')

  if (!stripeKey) {
    // No-payment mode: activate the campaign now so it serves immediately.
    await supabase.from('advertisers')
      .update({ paid: true, status: 'active' })
      .eq('ad_id', adv.ad_id)
    return json(200, { activated: true, dashboard_key: adv.dashboard_key, amount_cents: amount })
  }

  const dash = `${SITE_BASE}/dashboard.html?key=${adv.dashboard_key}`
  const form = new URLSearchParams()
  form.set('mode', 'payment')
  form.set('success_url', `${dash}&paid=1`)
  form.set('cancel_url', `${SITE_BASE}/advertise.html`)
  form.set('client_reference_id', adv.ad_id)
  form.set('metadata[ad_id]', adv.ad_id)
  if (adv.email) form.set('customer_email', adv.email)
  form.set('line_items[0][quantity]', '1')
  form.set('line_items[0][price_data][currency]', 'usd')
  form.set('line_items[0][price_data][unit_amount]', String(amount))
  form.set('line_items[0][price_data][product_data][name]',
    `Mango — ${adv.blocks} block${adv.blocks > 1 ? 's' : ''} (${(adv.blocks * 1000).toLocaleString()} impressions)`)
  form.set('line_items[0][price_data][product_data][description]',
    (adv.ad_text || adv.company || 'Spinner campaign').slice(0, 120))

  const resp = await fetch('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${stripeKey}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form.toString(),
  })
  const session = await resp.json()
  if (!resp.ok) return json(502, { error: 'stripe error', detail: session })
  return json(200, { url: session.url, id: session.id })
})
