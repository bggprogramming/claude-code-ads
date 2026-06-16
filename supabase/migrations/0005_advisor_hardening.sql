-- 0005_advisor_hardening.sql
-- Fixes from the end-to-end audit:
--   #2  funnel_summary: replace the SECURITY DEFINER *view* (linter 0010, ERROR)
--       with a SECURITY DEFINER *function* exposing the same PII-free aggregate to
--       anon, without granting any access to raw funnel_events rows. ops.html now
--       reads it via  GET /rest/v1/rpc/funnel_summary.
--   #3a processed_stripe_events: add an explicit deny-all policy so it is no longer
--       "RLS enabled, no policy" (linter 0008). Service role still bypasses RLS.
--
-- Not fixed here (reported instead):
--   • pg_net in public schema (linter 0014, WARN): pg_net does not support
--     ALTER EXTENSION ... SET SCHEMA, so it cannot be relocated without a
--     drop/recreate that would disrupt the advertiser-email trigger. Its API
--     stays in the dedicated `net` schema regardless, so net.http_post is safe.
--   • Auth leaked-password protection (WARN): an Auth config toggle, not SQL.

-- ── #2: funnel_summary view → definer function ──────────────────────────────
drop view if exists public.funnel_summary;

create or replace function public.funnel_summary()
returns table (
  step       text,
  events     bigint,
  users      bigint,
  first_seen timestamptz,
  last_seen  timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select step,
         count(*)             as events,
         count(distinct code) as users,
         min(ts)              as first_seen,
         max(ts)              as last_seen
  from public.funnel_events
  group by step
$$;

-- Only the anon role (the public ops dashboard) may call it; raw funnel_events
-- rows stay hidden by RLS. This is the intentional, reviewed public-aggregate
-- surface — the remaining "anon can execute SECURITY DEFINER function" advisor
-- WARN is expected and accepted (it replaces the old, ERROR-level definer view).
revoke execute on function public.funnel_summary() from public, authenticated;
grant  execute on function public.funnel_summary() to anon;

-- ── #3a: processed_stripe_events explicit deny-all ──────────────────────────
drop policy if exists "no_direct_access" on public.processed_stripe_events;
create policy "no_direct_access" on public.processed_stripe_events
  for all to anon, authenticated using (false) with check (false);
