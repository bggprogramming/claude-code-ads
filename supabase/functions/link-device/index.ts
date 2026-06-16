import { createClient } from 'jsr:@supabase/supabase-js@2'

// Link a device account into a primary account so their earnings aggregate in
// the portal. POST { code, device_code }:
//   • code        — the account you want to keep (the "primary")
//   • device_code — the other device's referral code, to fold into the primary
// Requires BOTH codes (each is that account's credential), so a user can only
// merge their own devices. Idempotent. Service-role only (anon has no UPDATE on
// users). Past AND future events from the device then roll up to the primary.

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json' } })

const norm = (s: unknown) => String(s ?? '').trim().toLowerCase().replace(/[^a-z0-9]/g, '')

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  let body: any = {}
  try { body = await req.json() } catch { return json(400, { error: 'invalid json' }) }
  const code       = norm(body.code)
  const deviceCode = norm(body.device_code)
  if (!code || !deviceCode) return json(400, { error: 'code and device_code required' })
  if (code === deviceCode)  return json(400, { error: 'those are the same code' })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })

  const { data: primary } = await supabase
    .from('users').select('id, referral_code, linked_to').eq('referral_code', code).maybeSingle()
  if (!primary) return json(404, { error: 'primary code not found', code })

  const { data: device } = await supabase
    .from('users').select('id, referral_code, linked_to').eq('referral_code', deviceCode).maybeSingle()
  if (!device) return json(404, { error: 'device code not found', code: deviceCode })

  // The real primary (in case the code you signed in with is itself a device).
  const primaryId = primary.linked_to ?? primary.id
  if (device.id === primaryId) return json(400, { error: 'already the same account' })

  // Point the device at the primary, and re-home anything that was linked to the
  // device (so merging a former primary keeps its devices attached).
  const { error: e1 } = await supabase.from('users').update({ linked_to: primaryId }).eq('id', device.id)
  if (e1) return json(500, { error: 'link failed', detail: e1.message })
  await supabase.from('users').update({ linked_to: primaryId }).eq('linked_to', device.id)

  // Count what now rolls up, for a friendly confirmation.
  const { data: fam } = await supabase
    .from('users').select('id').or(`id.eq.${primaryId},linked_to.eq.${primaryId}`)
  const ids = (fam ?? []).map(f => f.id)
  const { data: roll } = await supabase.rpc('account_rollup', { p_ids: ids })   // SQL-side, no row cap
  const totalMc = roll?.total_mc ?? 0

  return json(200, {
    ok: true,
    linked: deviceCode,
    into: primary.referral_code,
    devices: ids.length,
    total_dollars: totalMc / 100_000,
  })
})
