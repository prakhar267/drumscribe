# Dodo Payments test-mode audit — 11 September 2026

This record contains no API keys, webhook signing secrets, checkout client
secrets, cookies, cardholder data or production customer data.

## Safety boundary

- Dodo remained visibly in **Test Mode** for the complete exercise.
- Only Dodo's published sandbox card number was submitted. No actual payment
  card was viewed, entered, selected, charged or authorized.
- No paid plan, paid infrastructure feature or real-money transaction was used.
- Public checkout remains disabled while Dodo merchant verification is pending.

## Test configuration

| Item | Non-secret value |
| --- | --- |
| Offer | One-time pack of 10 full-song transcription credits for USD 15 |
| Dodo test product | `pdt_0NnK4Qfm2vKzBmmpU4hOO` |
| Webhook endpoint | `https://drumtoscore.com/api/v1/billing/webhooks/dodo` |
| Dodo test endpoint ID | `ep_3J9V7vBTD1QrDXAhA40KOPCmqzk` |
| Subscribed events | `payment.succeeded`, `refund.succeeded` |
| Application billing mode | Dodo `test_mode` |
| Public checkout flag | disabled |

The test API key and webhook signing secret are stored only in the root-owned
production environment file with mode `0600`. The local Dodo CLI keeps its test
credential encrypted. Neither value is committed to Git.

## End-to-end evidence

1. A production API checkout request created a Dodo test checkout for a
   synthetic verified user.
2. Dodo displayed its **Test Mode** banner and test-card documentation.
3. The checkout completed successfully with Dodo's published US sandbox Visa
   number and a matching synthetic US billing address.
4. Dodo emitted `payment.succeeded` for the configured product and returned the
   browser to `https://drumtoscore.com/billing/success`.
5. The signed webhook replay returned HTTP `200`.
6. The Neon purchase changed from `PENDING` to `PAID`; the user and purchase
   balances both became exactly `10`; provider payment and webhook IDs were
   recorded.
7. Replaying the identical event returned HTTP `200` again while both balances
   remained `10`, proving idempotent credit fulfillment.
8. Three exact synthetic `billing-e2e-…@example.com` users created for the test
   were deleted after verification; zero matching synthetic users remain.

## Configuration correction and recovery

The first signed delivery returned HTTP `401` because the production server had
the wrong webhook signing secret. The endpoint-specific Dodo test secret was
copied without displaying it, compared by SHA-256, and installed securely.

During that secret replacement, an environment-file serialization mistake
briefly caused the API to start with defaults and return `502`/`400`. The
pre-change backup was immediately restored, the update was reapplied as an
80-line file, and the API was recreated. Final readiness passed with PostgreSQL,
queue, private object storage and model provider all reporting `ok`.

## Live-launch status update — 12 September 2026

The owner subsequently completed Dodo's product, identity and bank steps. Dodo
now shows live payments active while its review is pending. Live resources were
prepared without activating the public Buy button; see
`docs/audit/dodo-live-staging-2026-09-12.md`. This test-mode audit does not
authorize any actual card or real charge.
