import { createClient } from 'jsr:@supabase/supabase-js@2'

// Resolve a signed-in user (e.g. via Google OAuth) to their developer account.
// The caller passes their Supabase Auth access token; we verify it, read the
// authenticated email, and return the matching users.referral_code. This is how
// "Sign in with Google" maps to an existing CLI account (linked by email).

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
}
const json = (s: number, b: unknown) =>
  new Response(JSON.stringify(b), { status: s, headers: { ...cors, 'Content-Type': 'application/json' } })

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: cors })

  const auth = req.headers.get('Authorization') ?? ''
  const jwt  = auth.replace(/^Bearer\s+/i, '').trim()
  if (!jwt) return json(401, { error: 'no token' })

  // Validate the user's token and read their identity (works for any provider).
  const anon = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_ANON_KEY') ?? '',
    { auth: { persistSession: false } })
  const { data: { user }, error } = await anon.auth.getUser(jwt)
  if (error || !user?.email) return json(401, { error: 'not authenticated' })

  // Find the developer account linked to this email.
  const svc = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })
  const { data } = await svc
    .from('users').select('referral_code').ilike('email', user.email).maybeSingle()

  if (!data) return json(404, { error: 'no_account', email: user.email })
  return json(200, { referral_code: data.referral_code, email: user.email })
})
