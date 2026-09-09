# DrumToScore billing launch runbook

This is the handoff record for the freemium and Dodo Payments implementation. It contains no
credentials, card information or customer payment data. Keep production billing disabled until
every external item below is supplied and the test-mode acceptance flow passes.

## Product rules implemented

- A verified account receives one complete transcription at no charge.
- Gmail and Googlemail dot/plus aliases share the same free-song claim.
- The free-song claim survives account deletion as a keyed HMAC and used timestamp; the email is not
  copied into the anti-abuse claim.
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

## External inputs still required

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

## Safe activation sequence

1. Back up the database and apply Alembic migrations.
2. Run `uv run python -m drumscribe_api.ops backfill-free-transcription-claims` once. It is idempotent.
3. Configure the Dodo values with `DRUMSCRIBE_DODO_PAYMENTS_ENVIRONMENT=test_mode` and keep the web
   checkout flag off.
4. In test mode, verify: one free song, second song blocked, checkout idempotency, signed success,
   ten credits, paid reservation, failed-job return, full refund, duplicate event, and stale-success
   replay after refund.
5. Verify audit records and balances directly in the database, then complete a restore rehearsal.
6. Change to `live_mode` only after Dodo confirms the product, webhook and merchant account are live.
7. Enable the web checkout flag in a new web deployment. Monitor webhook 4xx/5xx responses and
   credit-balance reconciliation during the first purchases.

Official references: [Dodo checkout sessions](https://docs.dodopayments.com/api-reference/checkout-sessions/create),
[webhook events](https://docs.dodopayments.com/developer-resources/webhooks/intents/webhook-events-guide),
and [refund payload](https://docs.dodopayments.com/developer-resources/webhooks/intents/refund).
