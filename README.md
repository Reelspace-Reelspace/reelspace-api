# ReelSpace Automation on Render (FastAPI)

This starter deploys an API that:
1) Receives a normalized payment webhook (from Wave via Pipedream/Make).
2) Logs the payment in Postgres and Google Sheets.
3) Sends a Plex friend invite (idempotency-safe).

## Deploy on Render
1. Create a new **Web Service** from this repo/zip. Choose **Python**.
2. Set **Build Command**: `pip install -r requirements.txt`
3. Set **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Add a **PostgreSQL** add-on (or external DB) and set `DATABASE_URL`.
5. Create env vars:
   - `PLEX_TOKEN` – a Plex token for an account that owns your server.
   - `PLEX_SERVER_NAME` – exactly as it appears in Plex resources.
   - `GOOGLE_SERVICE_ACCOUNT_JSON` – full JSON for a service account with Sheets access.
   - `GOOGLE_SHEET_ID` – the target Sheet ID; share it with the service account email.
   - `SHARED_WEBHOOK_SECRET` – any string; also used to sign the webhook in Pipedream/Make.
   - `DEFAULT_PLAN_PRICE` (optional) – default monthly price (e.g., `7.00`).
   - `DEFAULT_PLAN_NAME` (optional) – default plan name.

6. First deploy; then GET `/healthz` to verify it’s running.

## Webhook Normalization
Use Pipedream/Make/Zapier to transform a Wave "payment received" into this JSON payload POSTed to:
`POST https://<your-render-service>/webhooks/wave`

```
{
  "event_type": "payment_succeeded",
  "provider_event_id": "wave-evt-123",
  "email": "user@example.com",
  "full_name": "User Name",
  "amount": 7.00,
  "currency": "USD",
  "period_start": "2025-11-01",
  "period_end": "2025-12-01",
  "referral_code": "REF-ABC123"
}
```

Include header: `X-Signature: <HMAC_SHA256(body, SHARED_WEBHOOK_SECRET)>`

## Idempotency & Dupes
- We `UNIQUE`-index `provider_event_id` and `idempotency_key` so replays don’t create duplicates.
- We only send a Plex invite if the user’s `plex_invite_status` is neither `sent` nor `accepted`.

## Google Sheets
- Set `GOOGLE_SERVICE_ACCOUNT_JSON` and `GOOGLE_SHEET_ID` env vars.
- The API appends rows to a worksheet named **Payments**. Create it (or it will be created automatically).

## Local Testing
```
uvicorn app.main:app --reload
curl -X POST http://localhost:8000/webhooks/wave   -H "Content-Type: application/json"   -d '{"event_type":"payment_succeeded","provider_event_id":"local-evt-1","email":"demo@example.com","amount":7,"currency":"USD","period_start":"2025-11-01","period_end":"2025-12-01"}'
```

## Notes
- This uses `plexapi` and a Plex **token** (safer than storing password).
- You can extend `/webhooks/wave` to handle refunds/failed payments and disable shares accordingly.
