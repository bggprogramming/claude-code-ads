import { createClient } from 'jsr:@supabase/supabase-js@2'

// Attach (or update) a developer's optional email, keyed by referral code.
// Used for payout notifications + earnings recovery. Service-role write only
// (anon can't UPDATE users), so this is the sanctioned path.

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json' } })

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  let body: any = {}
  try { body = await req.json() } catch { return json(400, { error: 'invalid json' }) }
  const code  = String(body.code ?? '').trim().toLowerCase()
  const email = String(body.email ?? '').trim()
  if (!code)              return json(400, { error: 'code required' })
  if (!EMAIL_RE.test(email) || email.length > 200) return json(400, { error: 'invalid email' })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })

  const { data, error } = await supabase
    .from('users').update({ email }).eq('referral_code', code).select('referral_code')
  if (error)            return json(500, { error: 'update failed', detail: error.message })
  if (!data || !data.length) return json(404, { error: 'not found' })
  return json(200, { ok: true })
})
