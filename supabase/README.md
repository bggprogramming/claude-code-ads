# Supabase backend (source of truth)

The whole backend for Mango, reproducible from this directory:

- `migrations/0001_init.sql` — full schema: tables, RLS, auction model, triggers,
  storage bucket, grants, `public_stats` view.
- `functions/*/index.ts` — the 9 edge functions.

All functions use `verify_jwt = false` (they're public endpoints) and rely on the
auto-injected `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`. Security is enforced in
the function bodies (recipient/earnings always resolved server-side) and by RLS.

## Functions

| Function | Purpose |
|---|---|
| `track-event` | **Only** writer of `events`. Computes developer earnings server-side (impression = 90% of bid; click = 50× the impression rate). Handles milestone + referral bonus. |
| `ad-feed` | House ads + active paid campaigns, bid-ordered, with a sha256 integrity hash. Consumed by `feed.py`. |
| `bid-market` | Live market snapshot: clearing price, ads live, imps/min, leaderboard, price-history chart series. |
| `create-checkout` | Stripe Checkout session for a campaign. No-payment mode (auto-activate) until `STRIPE_SECRET_KEY` is set. |
| `stripe-webhook` | Marks a campaign paid+active on `checkout.session.completed` (verifies signature; 503 until `STRIPE_WEBHOOK_SECRET` set). |
| `campaign-manage` | Advertiser self-service (pause/resume/set_bid/add_blocks), authed by `dashboard_key`. |
| `dev-portal` | Developer earnings/referrals/payout data, keyed by referral code. |
| `advertiser-portal` | Account-level advertiser view: all campaigns + analytics for the email behind a given `dashboard_key`. |
| `badge` | Shields.io endpoint badge of a developer's lifetime earnings. |
| `send-dashboard-email` | Emails an advertiser their dashboard link via Resend (requires `RESEND_API_KEY`). |

## Deploy

```bash
supabase link --project-ref gpbrzpyvzlzwvvymgeyk
supabase db push                         # apply migrations
supabase functions deploy                # deploy all functions
# or one at a time:
supabase functions deploy track-event --no-verify-jwt
```

## Secrets

```bash
supabase secrets set RESEND_API_KEY=re_...                 # enables advertiser dashboard email
supabase secrets set EMAIL_FROM="Mango <ads@yourdomain.com>"   # after domain verification
supabase secrets set STRIPE_SECRET_KEY=sk_...              # flips checkout to real payment
supabase secrets set STRIPE_WEBHOOK_SECRET=whsec_...       # enables the paid→active webhook
supabase secrets set SITE_BASE="https://your-site"         # if the marketing site moves
```

Without `STRIPE_SECRET_KEY`, `create-checkout` runs in **no-payment mode**: campaigns
activate immediately on creation. Setting the key reverts to payment-gated.

See `../EMAIL_SETUP.md` for the full email go-live runbook.
