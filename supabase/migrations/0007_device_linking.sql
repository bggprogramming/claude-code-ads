-- 0007_device_linking.sql
-- Earnings were keyed per-device (each install created its own users row +
-- referral_code), so a developer using Mango on several machines saw their
-- earnings split across unconnected accounts. Add an optional self-link: a
-- device account can point at a primary account via users.linked_to, and the
-- portal then aggregates events across the primary + all devices linked to it.
-- Linking is performed only by the service-role link-device function (anon has
-- no UPDATE on users), and requires knowing BOTH referral codes (each code is
-- that account's credential), so a user can only merge their own devices.
alter table public.users
  add column if not exists linked_to text references public.users(id) on delete set null;

create index if not exists users_linked_to_idx on public.users(linked_to);
