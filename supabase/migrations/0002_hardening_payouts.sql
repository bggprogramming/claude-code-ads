-- 0002 — Security hardening + developer payouts (Stripe Connect).
--   1. Replace permissive anon INSERT policies (WITH CHECK true) with validated,
--      scoped ones. Critically: anon can no longer insert paid=true advertisers
--      (which would have served free ads).
--   2. processed_stripe_events table → webhook idempotency / replay protection.
--   3. payouts table + users.stripe_account_id/payouts_enabled → cash-out path.

-- ── 1. Tighten anon INSERT policies ─────────────────────────────────────────
drop policy if exists "anon insert users" on public.users;
create policy "anon insert users" on public.users for insert to anon
  with check (
    char_length(id) between 8 and 64
    and char_length(referral_code) between 4 and 32
    and coalesce(milestone_hit, false) = false       -- can't self-mark milestone
  );

drop policy if exists "anon insert advertisers" on public.advertisers;
create policy "anon insert advertisers" on public.advertisers for insert to anon
  with check (
    paid = false                                     -- can't self-activate (free ads)
    and status in ('pending','active','paused')
    and char_length(ad_text) between 1 and 200
    and char_length(email)   between 3 and 200
    and char_length(url)     between 3 and 500
    and bid_per_block_cents >= 100
    and blocks between 1 and 100000
  );

drop policy if exists "anon insert session_contexts" on public.session_contexts;
create policy "anon insert session_contexts" on public.session_contexts for insert to anon
  with check (
    char_length(user_id) between 1 and 64
    and char_length(coalesce(prompt_snippet, '')) <= 300
  );

drop policy if exists "anon insert leads" on public.ad_leads;
create policy "anon insert leads" on public.ad_leads for insert to anon
  with check (
    char_length(coalesce(ad_text, '')) <= 500
    and char_length(coalesce(email,  '')) <= 200
    and char_length(coalesce(url,    '')) <= 500
    and char_length(coalesce(budget, '')) <= 100
  );

-- ── 2. Stripe webhook idempotency ───────────────────────────────────────────
create table if not exists public.processed_stripe_events (
  event_id     text primary key,
  processed_at timestamptz default now()
);
alter table public.processed_stripe_events enable row level security;
-- no anon policies → only the service-role webhook may read/write.

-- ── 3. Developer payouts (Stripe Connect) ───────────────────────────────────
alter table public.users add column if not exists stripe_account_id text;
alter table public.users add column if not exists payouts_enabled   boolean default false;

create table if not exists public.payouts (
  id                bigint generated always as identity primary key,
  user_id           text not null,
  amount_millicents bigint not null,
  status            text not null default 'pending'
                      check (status in ('pending','paid','failed')),
  stripe_transfer_id text,
  note              text,
  created_at        timestamptz default now(),
  paid_at           timestamptz
);
create index if not exists payouts_user_idx on public.payouts (user_id);
alter table public.payouts enable row level security;
-- public read so the portal/dev-portal can surface payout history; writes are
-- service-role only (payout-request edge function).
create policy "anon select payouts" on public.payouts for select to anon using (true);

-- Expose the two new non-sensitive users columns to anon reads (id/referral_code
-- etc. are already readable via the table's public select policy).
