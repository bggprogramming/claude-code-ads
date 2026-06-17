import { createClient } from 'jsr:@supabase/supabase-js@2'

// Find-or-create a developer account by email — the single identity anchor
// (same model as Google sign-in / whoami, just for the CLI + extension install).
// Every machine that signs in with the same email shares ONE account, so earnings
// aggregate with no per-device codes and no linking step. POST { email, referred_by? }.

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json' } })

const ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789'
function genCode(): string {
  let c = ''
  for (let i = 0; i < 6; i++) c += ALPHABET[Math.floor(Math.random() * 36)]
  return c
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  let body: any = {}
  try { body = await req.json() } catch { return json(400, { error: 'invalid json' }) }
  const email = String(body.email ?? '').trim().toLowerCase()
  if (!email || !email.includes('@') || email.includes(' ')) return json(400, { error: 'valid email required' })
  const referredBy = body.referred_by ? String(body.referred_by).trim().toLowerCase().replace(/[^a-z0-9]/g, '') : null

  const svc = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })

  // Already an account for this email? Return it (oldest wins if there are dupes).
  const existing = async () => {
    const { data } = await svc.from('users')
      .select('id, referral_code, linked_to')
      .ilike('email', email).order('created_at', { ascending: true }).limit(1)
    return data?.[0] ?? null
  }
  let found = await existing()
  if (found) {
    // If that account is itself a linked device, hand back the primary's code.
    let code = found.referral_code
    if (found.linked_to) {
      const { data: p } = await svc.from('users').select('referral_code').eq('id', found.linked_to).maybeSingle()
      if (p?.referral_code) code = p.referral_code
    }
    return json(200, { user_id: found.id, referral_code: code, existing: true })
  }

  // Create a new account keyed by this email.
  const id = crypto.randomUUID()
  for (let attempt = 0; attempt < 6; attempt++) {
    const code = genCode()
    const { error } = await svc.from('users').insert({ id, referral_code: code, email, referred_by: referredBy })
    if (!error) return json(200, { user_id: id, referral_code: code, existing: false })
    // Referral-code collision → try another code.
    if ((error as any).code === '23505') {
      const again = await existing()              // lost a race on the same email?
      if (again) return json(200, { user_id: again.id, referral_code: again.referral_code, existing: true })
      continue                                    // else it was a code clash; retry
    }
    return json(500, { error: 'create failed', detail: error.message })
  }
  return json(500, { error: 'could not allocate a code, try again' })
})
