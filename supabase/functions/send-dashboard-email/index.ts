import { createClient } from 'jsr:@supabase/supabase-js@2'

// Emails the advertiser their dashboard link via Resend. Recipient is ALWAYS the
// email on the resolved DB row (never client-supplied) — can't be an open relay.
// Idempotent via advertisers.dashboard_emailed_at unless {force:true}.
// Requires the RESEND_API_KEY secret; EMAIL_FROM / SITE_BASE are optional env.

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}

const SITE_BASE  = Deno.env.get('SITE_BASE')  ?? 'https://bggprogramming.github.io/claude-code-ads'
const EMAIL_FROM = Deno.env.get('EMAIL_FROM') ?? 'Claude Code Ads <onboarding@resend.dev>'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } })

function esc(s: string): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })
  if (req.method !== 'POST')   return json(405, { error: 'method not allowed' })

  const resendKey = Deno.env.get('RESEND_API_KEY')
  if (!resendKey) return json(500, { error: 'RESEND_API_KEY not configured', hint: 'Add it as a Supabase secret.' })

  let body: any = {}
  try { body = await req.json() } catch { /* empty ok */ }
  const rec = body?.record ?? body ?? {}
  const id = rec.id ?? null, dashboardKey = rec.dashboard_key ?? null, adId = rec.ad_id ?? null
  const force = body?.force === true
  if (!id && !dashboardKey && !adId) return json(400, { error: 'provide one of: id, dashboard_key, ad_id' })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '', Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } })

  let q = supabase.from('advertisers').select('id, company, email, ad_text, dashboard_key, cpm_cents, dashboard_emailed_at')
  if (id)                q = q.eq('id', id)
  else if (dashboardKey) q = q.eq('dashboard_key', dashboardKey)
  else                   q = q.eq('ad_id', adId)

  const { data: adv, error } = await q.maybeSingle()
  if (error)  return json(500, { error: 'db lookup failed', detail: error.message })
  if (!adv)   return json(404, { error: 'advertiser not found' })
  if (!adv.email)         return json(422, { error: 'advertiser has no email' })
  if (!adv.dashboard_key) return json(422, { error: 'advertiser has no dashboard_key' })
  if (adv.dashboard_emailed_at && !force)
    return json(200, { skipped: true, reason: 'already emailed', at: adv.dashboard_emailed_at, to: adv.email })

  const dashUrl = `${SITE_BASE}/dashboard.html?key=${adv.dashboard_key}`
  const company = esc(adv.company || 'there')
  const adText  = esc(adv.ad_text || '')

  const html = `<!doctype html><html><body style="margin:0;background:#0b0b0c;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#e7e7e9;padding:32px">
  <div style="max-width:520px;margin:0 auto;background:#151517;border:1px solid #232327;border-radius:14px;padding:32px">
    <div style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#b4ff69;font-weight:600">Claude Code Ads</div>
    <h1 style="font-size:22px;margin:14px 0 6px;color:#fff">Your campaign is live 🎉</h1>
    <p style="font-size:15px;line-height:1.5;color:#b8b8bd;margin:0 0 22px">Hi ${company}, your ad is now in rotation across developer terminals. Track impressions, clicks, and CTR from your private dashboard — bookmark this link, it's the only way back in.</p>
    <a href="${dashUrl}" style="display:inline-block;background:#b4ff69;color:#0b0b0c;font-weight:600;font-size:15px;text-decoration:none;padding:13px 22px;border-radius:9px">Open your dashboard →</a>
    <div style="margin:22px 0 0;padding:16px;background:#0e0e10;border:1px solid #232327;border-radius:9px">
      <div style="font-size:11px;color:#76767c;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Your ad</div>
      <div style="font-size:14px;color:#e7e7e9">${adText}</div>
    </div>
    <p style="font-size:12px;color:#76767c;margin:22px 0 0;word-break:break-all">Dashboard link: <a href="${dashUrl}" style="color:#b4ff69">${dashUrl}</a></p>
  </div>
</body></html>`

  const text = `Your Claude Code Ads campaign is live.\n\nHi ${adv.company || 'there'}, your ad is now in rotation. Track performance from your private dashboard (bookmark it):\n\n${dashUrl}\n\nYour ad: ${adv.ad_text || ''}`

  const resp = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${resendKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: EMAIL_FROM, to: [adv.email], subject: 'Your Claude Code Ads dashboard', html, text }),
  })
  const result = await resp.json().catch(() => ({}))
  if (!resp.ok) return json(502, { error: 'resend send failed', status: resp.status, detail: result })

  await supabase.from('advertisers').update({ dashboard_emailed_at: new Date().toISOString() }).eq('id', adv.id)
  return json(200, { sent: true, to: adv.email, email_id: result?.id ?? null, dashboard: dashUrl })
})
