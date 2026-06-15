import { createClient } from 'jsr:@supabase/supabase-js@2'

// Advertiser self-service campaign management. Authenticated by the campaign's
// secret dashboard_key (an unguessable UUID). Actions: pause, resume, set_bid,
// add_blocks. Returns the updated campaign + its current market rank.

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json' } })

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  let body: any = {}
  try { body = await req.json() } catch { return json(400, { error: 'invalid json' }) }
  const key    = String(body.dashboard_key ?? '').trim()
  const action = String(body.action ?? '').trim()
  if (!key) return json(400, { error: 'dashboard_key required' })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })

  const { data: adv } = await supabase
    .from('advertisers')
    .select('id, ad_id, status, paid, bid_per_block_cents, blocks, impressions_delivered')
    .eq('dashboard_key', key).maybeSingle()
  if (!adv) return json(404, { error: 'campaign not found' })

  const patch: any = {}
  if (action === 'pause') {
    patch.status = 'paused'
  } else if (action === 'resume') {
    if (!adv.paid) return json(400, { error: 'campaign is not paid' })
    patch.status = adv.impressions_delivered >= adv.blocks * 1000 ? 'exhausted' : 'active'
  } else if (action === 'set_bid') {
    const cents = Math.round(Number(body.bid_per_block_cents))
    if (!Number.isFinite(cents) || cents < 100) return json(400, { error: 'bid must be ≥ $1.00 (100 cents)' })
    patch.bid_per_block_cents = cents
  } else if (action === 'add_blocks') {
    const add = Math.round(Number(body.blocks))
    if (!Number.isFinite(add) || add < 1 || add > 1000) return json(400, { error: 'blocks must be 1–1000' })
    patch.blocks = adv.blocks + add
    if (adv.status === 'exhausted') patch.status = 'active'   // more inventory → live again
  } else {
    return json(400, { error: 'unknown action' })
  }

  const { error } = await supabase.from('advertisers').update(patch).eq('id', adv.id)
  if (error) return json(500, { error: 'update failed', detail: error.message })

  // Recompute market rank among live campaigns.
  const { data: live } = await supabase
    .from('advertisers').select('ad_id, bid_per_block_cents, blocks, impressions_delivered')
    .eq('status', 'active').eq('paid', true)
  const ranked = (live ?? [])
    .filter((c: any) => c.impressions_delivered < c.blocks * 1000)
    .sort((a: any, b: any) => b.bid_per_block_cents - a.bid_per_block_cents)
  const rank = ranked.findIndex((c: any) => c.ad_id === adv.ad_id)

  const { data: updated } = await supabase
    .from('advertisers')
    .select('ad_id, status, paid, bid_per_block_cents, blocks, impressions_delivered')
    .eq('id', adv.id).maybeSingle()

  return json(200, { ok: true, campaign: updated, rank: rank >= 0 ? rank + 1 : null, live_count: ranked.length })
})
