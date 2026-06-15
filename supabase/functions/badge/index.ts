import { createClient } from 'jsr:@supabase/supabase-js@2'

// Shields.io endpoint badge: a developer's lifetime earnings, by referral code.
// GET /badge/<referral_code>  →  { schemaVersion, label, message, color, ... }

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  const url = new URL(req.url)
  const parts = url.pathname.split('/')
  const referralCode = parts[parts.length - 1]?.trim()

  const badgeResponse = (message: string, color: string, cached = true) =>
    new Response(JSON.stringify({
      schemaVersion: 1,
      label:         'earned · claude code ads',
      message,
      color,
      logoSvg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23b4ff69"><circle cx="12" cy="12" r="10"/></svg>',
      style: 'flat',
    }), {
      headers: {
        ...corsHeaders,
        'Content-Type':  'application/json',
        'Cache-Control': cached ? 'max-age=300, s-maxage=300' : 'no-cache',
      },
    })

  if (!referralCode || referralCode === 'badge') {
    return badgeResponse('$0.00', 'lightgrey', false)
  }

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')              ?? '',
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } }
  )

  const { data: user } = await supabase
    .from('users').select('id').eq('referral_code', referralCode).maybeSingle()
  if (!user) return badgeResponse('$0.00', 'blue', true)

  // Total developer earnings = all events (impressions + clicks).
  const { data: rows } = await supabase
    .from('events').select('earnings_millicents').eq('user_id', user.id)

  const totalMc  = (rows ?? []).reduce((s: number, r: any) => s + (r.earnings_millicents ?? 0), 0)
  const dollars  = totalMc / 100_000
  const message  = `$${dollars.toFixed(2)}`
  const color    = dollars >= 10 ? 'brightgreen'
                 : dollars >= 1  ? 'green'
                 : dollars >= 0.01 ? 'yellow'
                 : 'lightgrey'

  return badgeResponse(message, color)
})
