# DrumToScore billing launch runbook

This is the handoff record for the freemium and Dodo Payments implementation. It contains no
credentials, card information or customer payment data. Dodo verification completed and production
billing was activated on 14 September 2026 after every external item below was supplied and the
test-mode acceptance flow passed.

## Product rules implemented

- Any user can process a recording up to 30 seconds at no charge.
- Legacy free-song claims remain stored only for backward-compatible migrations; they no longer
  grant a complete-song transcription.
- Processing reserves an entitlement atomically. Repeated request keys and job retries do not spend
  twice. A failed or cancelled job returns its reservation.
- Paid credits are associated with their originating purchase pack.
- A signed `payment.succeeded` event grants the configured pack once.
- A signed, full `refund.succeeded` event revokes only unused credits from that purchase once.
- Partial refunds stop for manual reconciliation; do not issue partial refunds operationally until a
  documented fractional-credit policy exists.
- Billing remains server-authoritative. Return-page query parameters never grant credits.

## Data written by billing

`credit_purchases` stores the internal user and purchase IDs, client idempotency key, Dodo checkout,
payment and refund IDs, status, configured pack size, remaining/revoked credit counts, webhook ID,
and paid/refunded timestamps. It never stores card numbers, CVV, bank credentials or provider API
secrets. `processing_jobs.credit_purchase_id` records which pack funded a paid job.

`free_transcription_claims` stores a keyed HMAC identity and the free-use timestamp. Users store the
matching claim hash and aggregate paid-credit balance. Secret values remain in server environment
configuration and must not be copied into this document, Git, logs or support tickets.

## External inputs supplied

1. Approved Dodo Payments merchant account. Stop if onboarding asks for a credit card or any paid
   upgrade; the owner must decide separately.
2. A live one-time product for exactly **10 transcription credits for USD 15**, including the final
   tax/refund configuration and its product ID.
3. A restricted server API key and webhook signing key.
4. Webhook endpoint:
   `https://drumtoscore.com/api/v1/billing/webhooks/dodo`, subscribed to
   `payment.succeeded` and `refund.succeeded`.
5. Merchant legal, tax, payout-bank and identity verification completed by the owner. These values
   must be entered only in Dodo's trusted dashboard, never sent through source code or chat.

## Production activation result

- A temporary Neon branch was created before the configuration change.
- The root-only Oracle environment was backed up and atomically promoted to Dodo `live_mode`.
- API readiness passed, a no-charge live checkout session returned HTTP `201`, and its hosted page
  displayed the expected DrumToScore USD 15 offer.
- Invalid webhook signatures remained fail-closed with HTTP `401`.
- Cloudflare Worker version `03a3fb2c-9ec2-4bac-aaa6-17fae9baba6a` enabled the public Buy action.
- No real card or payment was used. Monitor the first genuine signed live payment webhook and verify
  that it grants exactly 10 credits once.

## Safe activation sequence

1. Back up the database and apply Alembic migrations.
2. Run `uv run python -m drumscribe_api.ops backfill-free-transcription-claims` once. It is idempotent.
3. Configure the Dodo values with `DRUMSCRIBE_DODO_PAYMENTS_ENVIRONMENT=test_mode` and keep the web
   checkout flag off.
4. In test mode, verify: 30-second preview, longer song requires credit, checkout idempotency, signed success,
   ten credits, paid reservation, failed-job return, full refund, duplicate event, and stale-success
   replay after refund.
5. Verify audit records and balances directly in the database, then complete a restore rehearsal.
6. Change to `live_mode` only after Dodo confirms the product, webhook and merchant account are live.
7. Enable the web checkout flag in a new web deployment. Monitor webhook 4xx/5xx responses and
   credit-balance reconciliation during the first purchases.

Official references: [Dodo checkout sessions](https://docs.dodopayments.com/api-reference/checkout-sessions/create),
[webhook events](https://docs.dodopayments.com/developer-resources/webhooks/intents/webhook-events-guide),
and [refund payload](https://docs.dodopayments.com/developer-resources/webhooks/intents/refund).
