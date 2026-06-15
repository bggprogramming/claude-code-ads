-- 0004 — Expose aggregate-only funnel + public stats for an internal ops page.
-- funnel_summary returns counts per step (no codes/PII); run as owner so anon
-- can read the aggregate without access to the raw funnel_events rows.
alter view public.funnel_summary set (security_invoker = off);
grant select on public.funnel_summary to anon;
grant select on public.public_stats  to anon;
