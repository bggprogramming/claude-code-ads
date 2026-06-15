import { createClient } from 'jsr:@supabase/supabase-js@2'

// Stripe webhook: on checkout.session.completed, mark the campaign paid + active.
// Verifies the Stripe signature with STRIPE_WEBHOOK_SECRET. Build-ready: returns
// 503 until the secret is configured (so it never trusts unsigned events).

async function verifyStripeSig(payload: string, header: string, secret: string): Promise<boolean> {
  // header: "t=timestamp,v1=signature[,v1=...]"
  const parts = Object.fromEntries(header.split(',').map(kv => kv.split('=')))
  const t = parts['t']; const v1 = parts['v1']
  if (!t || !v1) return false
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  const mac = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${t}.${payload}`))
  const expected = Array.from(new Uint8Array(mac)).map(b => b.toString(16).padStart(2, '0')).join('')
  if (expected.length !== v1.length) return false
  let diff = 0
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ v1.charCodeAt(i)
  return diff === 0
}

Deno.serve(async (req: Request) => {
  if (req.method !== 'POST') return new Response('method not allowed', { status: 405 })

  const secret = Deno.env.get('STRIPE_WEBHOOK_SECRET')
  if (!secret) return new Response('webhook not configured', { status: 503 })

  const sig = req.headers.get('stripe-signature') ?? ''
  const raw = await req.text()
  if (!(await verifyStripeSig(raw, sig, secret))) {
    return new Response('bad signature', { status: 400 })
  }

  let evt: any
  try { evt = JSON.parse(raw) } catch { return new Response('bad json', { status: 400 }) }

  if (evt.type === 'checkout.session.completed') {
    const adId = evt.data?.object?.metadata?.ad_id || evt.data?.object?.client_reference_id
    if (adId) {
      const supabase = createClient(
        Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
        { auth: { persistSession: false } })
      await supabase.from('advertisers')
        .update({ paid: true, status: 'active' })
        .eq('ad_id', adId)
    }
  }
  return new Response(JSON.stringify({ received: true }), { headers: { 'Content-Type': 'application/json' } })
})
