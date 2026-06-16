-- 0006_users_self_register.sql
-- Bug: `users` had RLS enabled with NO policies, so anon INSERT was denied.
-- Fresh installs (setup.py register_supabase / the VS Code extension's
-- getOrCreateUser) silently failed to create their users row, so dev-portal
-- 404'd for them and the portal showed no impressions/earnings even though their
-- events were being recorded server-side.
--
-- Allow anon self-registration, but block pre-setting milestone / payout fields
-- (no earning- or payout-escalation). The id PK + referral_code UNIQUE
-- constraints reject duplicates. No anon SELECT is granted — dev-portal reads
-- users via the service role, so user rows (incl. stripe_account_id) stay private.
drop policy if exists "users_self_register" on public.users;
create policy "users_self_register" on public.users
  for insert to anon
  with check (
    coalesce(milestone_hit, false)       = false
    and stripe_account_id is null
    and coalesce(payouts_enabled, false) = false
  );
