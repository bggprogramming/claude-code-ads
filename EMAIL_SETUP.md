# Advertiser dashboard email — setup & go-live runbook

When someone creates a campaign on `advertise.html`, they should get an email with
their private dashboard link (`dashboard.html?key=<dashboard_key>`). This documents
how that pipeline is wired, how to turn it on in **test mode**, and the checklist to
take it to **production**.

---

## What's already built (no action needed)

| Piece | Name / location | Status |
|-------|-----------------|--------|
| Edge function (sends the email via Resend) | `send-dashboard-email` (Supabase) | ✅ deployed (v2) |
| Auto-trigger on new campaign | `trg_advertiser_email` on `public.advertisers` (uses `pg_net`) | ✅ active |
| Idempotency guard | `advertisers.dashboard_emailed_at` column | ✅ added |
| Success-screen confirmation | `advertise.html` ("We've emailed this link to …") | ✅ done |

- **Project ref:** `gpbrzpyvzlzwvvymgeyk`
- **Function URL:** `https://gpbrzpyvzlzwvvymgeyk.supabase.co/functions/v1/send-dashboard-email`
- **Security:** the recipient is **always** the email stored on the advertiser row
  (looked up by its UUID). The function never emails a client-supplied address, so it
  can't be abused as an open relay even though it's public (`verify_jwt = false`).
- **Idempotent:** a row is emailed once; retries are skipped unless you POST `{"force": true}`.

The pipeline is verified end-to-end. The **only** thing not done is providing the
Resend API key — until that secret exists, the function returns
`500 {"error":"RESEND_API_KEY not configured"}` (this is expected right now).

---

## PART A — Turn on TEST mode (sends only to dep224qa@gmail.com)

Resend's test sender (`onboarding@resend.dev`) only delivers to **your own Resend
account email**. So in test mode, only campaigns whose email is `dep224qa@gmail.com`
will actually arrive. Everything else 502s at Resend (harmless, logged).

### A1. Create a Resend account + API key
1. Go to <https://resend.com> and sign up **using `dep224qa@gmail.com`**.
2. Verify your email.
3. Go to **API Keys** → **Create API Key** (name it e.g. `mango`,
   permission **Sending access**). Copy the `re_...` value — shown once.

### A2. Store the key as a Supabase secret
Do **not** paste the key into chat. Use either:

**Option 1 — Supabase CLI (from your terminal):**
```bash
supabase secrets set RESEND_API_KEY=re_your_key_here --project-ref gpbrzpyvzlzwvvymgeyk
```
(If the CLI isn't logged in: `supabase login` first.)

**Option 2 — Dashboard:**
Supabase → your project → **Edge Functions** → **Secrets** (a.k.a. *Manage secrets*) →
add `RESEND_API_KEY` = `re_...` → save.

Secrets propagate to the function within a few seconds; no redeploy needed.

### A3. Test it
Fire a send for the existing `dep224qa@gmail.com` advertiser row (force, so it ignores
the idempotency guard):
```bash
curl -s -X POST \
  "https://gpbrzpyvzlzwvvymgeyk.supabase.co/functions/v1/send-dashboard-email" \
  -H "Content-Type: application/json" \
  -d '{"dashboard_key":"bb5a48fe-c930-4883-af18-cf86038163ad","force":true}'
```
Expected: `{"sent":true,"to":"dep224qa@gmail.com","email_id":"...","dashboard":"..."}`
and the email lands in that inbox. A real new campaign created via `advertise.html`
with that email will also arrive automatically (via the trigger).

> Once you've set the secret, tell me and I'll run this test for you and confirm delivery.

---

## PART B — Go-live checklist (before real advertisers)

The blocker for production is that the test sender can only reach your own inbox. To
email **arbitrary** advertisers you must send from a **domain you own and verify**.

### B1. Get a domain (skip if you already own one)
- Register a domain (~$10/yr) at Cloudflare Registrar, Namecheap, or Porkbun.
- You need DNS-record access for it (all registrars above provide this).
- `bggprogramming.github.io` does **not** count — you don't control its DNS.

### B2. Verify the domain in Resend
1. Resend → **Domains** → **Add Domain** → enter e.g. `yourdomain.com`
   (or a subdomain like `mail.yourdomain.com` — recommended, keeps root DNS clean).
2. Resend shows DNS records to add — typically:
   - **MX** (for the bounce/feedback subdomain)
   - **TXT (SPF)** — `v=spf1 include:...`
   - **TXT (DKIM)** — one or more `resend._domainkey...` records
3. Add those records in your registrar's DNS panel exactly as shown.
4. Back in Resend, click **Verify**. Propagation is usually minutes, up to ~48h.

### B3. Add a DMARC record (deliverability — strongly recommended)
Add a TXT record at `_dmarc.yourdomain.com`:
```
v=DMARC1; p=none; rua=mailto:dep224qa@gmail.com
```
Start with `p=none` (monitor), tighten to `p=quarantine` later once clean.

### B4. Point the function at your domain
Set the `EMAIL_FROM` secret (the function already reads it; defaults to the test sender):
```bash
supabase secrets set EMAIL_FROM="Mango <ads@yourdomain.com>" --project-ref gpbrzpyvzlzwvvymgeyk
```
The `from` address's domain **must** match the verified domain. No redeploy needed.

### B5. (If the marketing site ever moves to a custom domain)
The email links use `SITE_BASE`, default
`https://bggprogramming.github.io/mango`. If the site moves, update it:
```bash
supabase secrets set SITE_BASE="https://yournewsite.com" --project-ref gpbrzpyvzlzwvvymgeyk
```

### B6. Production smoke test
1. Create a real campaign on `advertise.html` using a **non-Gmail** address you control
   (e.g. an Outlook/work inbox) to confirm delivery to arbitrary recipients.
2. Check it didn't land in spam. If it did, recheck SPF/DKIM/DMARC alignment.
3. Verify the dashboard link in the email opens the right campaign.

### B7. Operational notes
- **Resend free tier:** ~3,000 emails/mo, 100/day. Upgrade before a launch spike.
- **Volume:** the trigger fires one email per campaign insert; well within limits.
- **Monitoring:** Resend dashboard shows delivery/bounce/complaint stats. Watch the
  complaint rate — high complaints hurt deliverability.
- **Reply handling:** add a `reply_to` in the function (currently none) if you want
  advertiser replies to reach a real inbox.

---

## Troubleshooting

| Symptom | Cause / fix |
|--------|-------------|
| `500 RESEND_API_KEY not configured` | Secret not set (Part A2). |
| `502 resend send failed` + `validation_error` "can only send to your own email" | Still on test sender; recipient ≠ your Resend account email. Finish Part B. |
| `502` + domain not verified | `EMAIL_FROM` domain isn't verified in Resend (Part B2/B4). |
| Email never arrives, no error | Check Resend dashboard logs + spam folder; verify DMARC/SPF. |
| Duplicate emails | Shouldn't happen (idempotent). To force a resend: POST `{"force":true}`. |

### Inspect what the trigger sent (server-side log)
```sql
select status_code, content, created
from net._http_response
order by created desc limit 5;
```

### Resend a link manually for any campaign
```bash
curl -s -X POST \
  "https://gpbrzpyvzlzwvvymgeyk.supabase.co/functions/v1/send-dashboard-email" \
  -H "Content-Type: application/json" \
  -d '{"dashboard_key":"<the-campaign-dashboard-key>","force":true}'
```
