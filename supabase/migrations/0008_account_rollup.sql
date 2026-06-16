-- 0008_account_rollup.sql
-- dev-portal summed earnings by fetching event rows into the edge function, but
-- PostgREST caps a response at ~1000 rows, so any account with >1000 events was
-- undercounted (e.g. a 2,535-impression device only reported ~1000). Aggregate
-- in SQL instead — no row cap, and far less data shipped. Returns one JSON blob
-- with lifetime totals + a by-surface breakdown for a set of (linked) user ids.
create or replace function public.account_rollup(p_ids text[])
returns json
language sql
stable
security definer
set search_path = public
as $$
  select json_build_object(
    'total_mc',     coalesce(sum(earnings_millicents), 0),
    'impressions',  count(*) filter (where event = 'impression'),
    'clicks',       count(*) filter (where event = 'click'),
    'click_mc',     coalesce(sum(earnings_millicents) filter (where event = 'click'), 0),
    'by_surface',   coalesce((
        select json_agg(json_build_object('surface', surface, 'impressions', imp, 'mc', mc) order by imp desc)
        from (
          select coalesce(surface, 'unknown') as surface,
                 count(*)                       as imp,
                 coalesce(sum(earnings_millicents), 0) as mc
          from public.events
          where user_id = any(p_ids) and event = 'impression'
          group by 1
        ) s
      ), '[]'::json)
  )
  from public.events
  where user_id = any(p_ids);
$$;

-- Internal helper for the service-role edge functions only.
revoke execute on function public.account_rollup(text[]) from public, anon, authenticated;
