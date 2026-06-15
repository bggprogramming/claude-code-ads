-- Claude Code Ads — consolidated schema (reproducible from scratch).
-- Captures the live state: tables, RLS, auction model, triggers, storage, grants.
-- Apply with: supabase db push   (or paste into the SQL editor on a fresh project)

create extension if not exists pg_net;

-- ──────────────────────────────────────────────────────────────────────────
-- Tables
-- ──────────────────────────────────────────────────────────────────────────

create table if not exists public.users (
  id            text primary key,                 -- pseudonymous client UUID
  referral_code text unique not null,
  referred_by   text,
  milestone_hit boolean default false,
  created_at    timestamptz default now()
);

create table if not exists public.events (
  id                  bigint generated always as identity primary key,
  ad_id               text not null,
  ad_text             text not null default '',
  event               text not null check (event in ('impression','click')),
  surface             text default 'unknown',
  user_id             text,
  earnings_millicents bigint default 0,           -- DEVELOPER's share, computed server-side
  variant             text default 'default',
  ts                  timestamptz default now()
);
create index if not exists events_user_idx on public.events (user_id);
create index if not exists events_ad_idx   on public.events (ad_id);

create table if not exists public.referral_bonuses (
  id                bigint generated always as identity primary key,
  referrer_code     text not null,
  referred_code     text not null,
  amount_millicents bigint default 1000000,       -- $10
  status            text default 'pending' check (status in ('pending','paid')),
  recipient         text default 'referrer' check (recipient in ('referrer','referred')),
  triggered_at      timestamptz default now(),
  paid_at           timestamptz,
  unique (referrer_code, referred_code, recipient) -- one row per party
);

create table if not exists public.ad_leads (
  id         bigint generated always as identity primary key,
  ad_text    text,
  url        text,
  budget     text,
  email      text,
  created_at timestamptz default now()
);

create table if not exists public.advertisers (
  id                    uuid primary key default gen_random_uuid(),
  ad_id                 text unique not null,
  company               text,                      -- optional (brand name)
  email                 text not null,
  ad_text               text not null,
  url                   text not null,
  -- auction model
  bid_per_block_cents   integer not null default 100,   -- $ per 1,000 impressions (min $1.00)
  blocks                integer not null default 1,     -- # of 1,000-impression blocks
  impressions_delivered integer not null default 0,
  show_on_leaderboard   boolean not null default true,
  paid                  boolean not null default false,
  status                text default 'active' check (status in ('pending','active','paused','exhausted')),
  -- creative
  logo_url              text,
  logo_path             text,                      -- Supabase Storage path
  use_variants          boolean default false,
  copy_variants         jsonb default '{}'::jsonb,
  -- legacy / housekeeping
  cpm_cents             integer not null default 2500,
  daily_budget_cents    integer not null default 50000,
  dashboard_key         uuid default gen_random_uuid(),  -- advertiser's secret portal token
  dashboard_emailed_at  timestamptz,
  created_at            timestamptz default now()
);

create table if not exists public.session_contexts (
  id              bigint generated always as identity primary key,
  user_id         text not null,
  session_id      text not null,
  cwd_hash        text,
  tech_stack      jsonb default '[]'::jsonb,
  tools_used      jsonb default '[]'::jsonb,
  file_extensions jsonb default '[]'::jsonb,
  prompt_snippet  text,
  ts              timestamptz default now()
);

create table if not exists public.bid_history (
  id                   bigint generated always as identity primary key,
  ts                   timestamptz not null default now(),
  clearing_price_cents integer not null,
  ads_live             integer not null default 0
);

-- ──────────────────────────────────────────────────────────────────────────
-- Row Level Security
--   Writes to events / referral_bonuses and updates to users go ONLY through
--   service-role edge functions (track-event), so earnings can't be forged.
--   anon may submit signup forms (users/advertisers/ad_leads/session_contexts)
--   and read non-sensitive data.
-- ──────────────────────────────────────────────────────────────────────────

alter table public.users            enable row level security;
alter table public.events           enable row level security;
alter table public.referral_bonuses enable row level security;
alter table public.ad_leads         enable row level security;
alter table public.advertisers      enable row level security;
alter table public.session_contexts enable row level security;
alter table public.bid_history      enable row level security;

-- users: public read + self-register; NO anon update (milestone set server-side)
create policy "anon select users" on public.users for select to anon using (true);
create policy "anon insert users" on public.users for insert to anon with check (true);

-- events: public read; NO anon insert (track-event writes via service role)
create policy "anon select" on public.events for select to anon using (true);

-- referral_bonuses: public read; NO anon insert (created server-side on milestone)
create policy "anon select bonuses" on public.referral_bonuses for select to anon using (true);

-- ad_leads: write-only intake form
create policy "anon insert leads" on public.ad_leads for insert to anon with check (true);

-- advertisers: public read (email column revoked below) + self-serve signup
create policy "anon select advertisers" on public.advertisers for select to anon using (true);
create policy "anon insert advertisers" on public.advertisers for insert to anon with check (true);

-- session_contexts: opt-in write only; NOT readable by anon (prompt privacy)
create policy "anon insert session_contexts" on public.session_contexts for insert to anon with check (true);

-- bid_history: public read (powers the market chart)
create policy "anon select bid_history" on public.bid_history for select to anon using (true);

-- Hide advertiser billing email from anon (re-grant every other column).
revoke select on public.advertisers from anon;
grant select (id, ad_id, company, ad_text, url, cpm_cents, daily_budget_cents,
              status, dashboard_key, created_at, logo_url, logo_path, use_variants,
              copy_variants, dashboard_emailed_at, bid_per_block_cents, blocks,
              impressions_delivered, show_on_leaderboard, paid)
  on public.advertisers to anon;

-- ──────────────────────────────────────────────────────────────────────────
-- Triggers (SECURITY DEFINER helpers; not callable via PostgREST RPC)
-- ──────────────────────────────────────────────────────────────────────────

-- Email the advertiser their dashboard link on signup (calls the edge function).
create or replace function public.notify_new_advertiser()
returns trigger language plpgsql security definer set search_path = public, extensions, net as $$
begin
  perform net.http_post(
    url     := 'https://gpbrzpyvzlzwvvymgeyk.supabase.co/functions/v1/send-dashboard-email',
    headers := jsonb_build_object('Content-Type','application/json'),
    body    := jsonb_build_object('id', NEW.id)
  );
  return NEW;
end; $$;
revoke execute on function public.notify_new_advertiser() from public, anon, authenticated;

drop trigger if exists trg_advertiser_email on public.advertisers;
create trigger trg_advertiser_email after insert on public.advertisers
  for each row execute function public.notify_new_advertiser();

-- Record a clearing-price point whenever the live auction changes (chart data).
create or replace function public.record_bid_history()
returns trigger language plpgsql security definer set search_path = public as $$
declare top_cents int; live_n int;
begin
  select coalesce(max(bid_per_block_cents),0), count(*)
    into top_cents, live_n
    from public.advertisers
    where status = 'active' and paid = true and impressions_delivered < blocks * 1000;
  insert into public.bid_history (clearing_price_cents, ads_live) values (top_cents, live_n);
  return null;
end; $$;
revoke execute on function public.record_bid_history() from public, anon, authenticated;

drop trigger if exists trg_bid_history on public.advertisers;
create trigger trg_bid_history
  after insert or update of bid_per_block_cents, status, paid, impressions_delivered
  on public.advertisers for each row execute function public.record_bid_history();

-- ──────────────────────────────────────────────────────────────────────────
-- Public aggregate view (runs as the caller, not definer)
-- ──────────────────────────────────────────────────────────────────────────
create or replace view public.public_stats as
  select round(coalesce(sum(earnings_millicents),0) / 100000.0, 2) as total_paid_dollars,
         count(distinct user_id) filter (where user_id is not null) as developer_count,
         count(*) filter (where event = 'impression')               as total_impressions
  from public.events;
alter view public.public_stats set (security_invoker = on);

-- ──────────────────────────────────────────────────────────────────────────
-- Storage: public brand-icons bucket (≤64 KB, images). Direct URLs only — no
-- broad SELECT policy, so the bucket can't be listed.
-- ──────────────────────────────────────────────────────────────────────────
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('brand-icons','brand-icons', true, 65536, array['image/png','image/jpeg','image/webp'])
on conflict (id) do update set public = true, file_size_limit = 65536,
  allowed_mime_types = array['image/png','image/jpeg','image/webp'];

drop policy if exists "anon upload brand icons" on storage.objects;
create policy "anon upload brand icons" on storage.objects
  for insert to anon with check (bucket_id = 'brand-icons');
