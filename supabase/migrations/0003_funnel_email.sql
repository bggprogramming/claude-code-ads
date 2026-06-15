-- 0003 — Optional developer email (payout + recovery) and funnel instrumentation.

-- ── Developer email (optional; for payouts, recovery, re-engagement) ─────────
alter table public.users add column if not exists email text;

-- Protect sensitive user columns from anon reads (email, stripe ids). anon keeps
-- read access to the pseudonymous columns the referral/portal flows need.
revoke select on public.users from anon;
grant  select (id, referral_code, referred_by, milestone_hit, created_at, payouts_enabled)
  on public.users to anon;

-- ── Funnel instrumentation ──────────────────────────────────────────────────
-- Lightweight onboarding/lifecycle events so the funnel can be measured:
--   installed → registered → optin_set → first_earning → referral_shared
--             → milestone → payout_requested
create table if not exists public.funnel_events (
  id   bigint generated always as identity primary key,
  code text,                       -- pseudonymous referral_code (nullable)
  step text not null,
  meta jsonb default '{}'::jsonb,
  ts   timestamptz default now()
);
create index if not exists funnel_step_idx on public.funnel_events (step);
create index if not exists funnel_ts_idx   on public.funnel_events (ts);

alter table public.funnel_events enable row level security;
-- write-only intake (like ad_leads); raw rows are not anon-readable.
create policy "anon insert funnel" on public.funnel_events for insert to anon
  with check (
    char_length(step) between 1 and 40
    and char_length(coalesce(code, '')) <= 32
  );

-- Aggregate-only view for funnel analysis (runs as the querying role; anon has
-- no row access, so only the owner/service role sees it — kept out of anon).
create or replace view public.funnel_summary as
  select step,
         count(*)                 as events,
         count(distinct code)     as users,
         min(ts)                  as first_seen,
         max(ts)                  as last_seen
  from public.funnel_events
  group by step;
alter view public.funnel_summary set (security_invoker = on);
