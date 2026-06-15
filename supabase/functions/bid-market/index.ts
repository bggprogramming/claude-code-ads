import { createClient } from 'jsr:@supabase/supabase-js@2'

// Live bid-market snapshot for the advertiser page: clearing price, ads live,
// impressions/min across the fleet, ranked leaderboard, and the price chart series.

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' },
  })

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')              ?? '',
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
    { auth: { persistSession: false } }
  )

  const { data: camps } = await supabase
    .from('advertisers')
    .select('ad_id, company, ad_text, url, logo_path, bid_per_block_cents, blocks, impressions_delivered, show_on_leaderboard')
    .eq('status', 'active').eq('paid', true)

  const live = (camps ?? []).filter((c: any) => c.impressions_delivered < c.blocks * 1000)
  const clearing = live.length ? Math.max(...live.map((c: any) => c.bid_per_block_cents)) : 0

  const leaderboard = live
    .filter((c: any) => c.show_on_leaderboard)
    .sort((a: any, b: any) => b.bid_per_block_cents - a.bid_per_block_cents)
    .map((c: any, i: number) => ({
      rank: i + 1,
      label: (c.ad_text || c.company || 'Advertiser'),
      company: c.company,
      logo_path: c.logo_path,
      bid_per_block_cents: c.bid_per_block_cents,
      impressions_delivered: c.impressions_delivered,
      impressions_target: c.blocks * 1000,
      status: 'live',
    }))

  // Impressions/min across the fleet, from the last hour of events.
  const since = new Date(Date.now() - 60 * 60 * 1000).toISOString()
  const { count } = await supabase
    .from('events').select('*', { count: 'exact', head: true })
    .eq('event', 'impression').gte('ts', since)
  const imps_per_min = Math.max(1, Math.round((count ?? 0) / 60))

  const { data: hist } = await supabase
    .from('bid_history').select('ts, clearing_price_cents')
    .order('ts', { ascending: true }).limit(500)

  return json(200, {
    clearing_price_cents: clearing,
    ads_live: live.length,
    imps_per_min,
    leaderboard,
    price_series: hist ?? [],
  })
})
