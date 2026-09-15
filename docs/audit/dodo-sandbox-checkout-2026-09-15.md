# Dodo sandbox checkout evidence — 15 September 2026

This record covers a real hosted Dodo **test-mode** checkout against the
DrumToScore API billing implementation. It did not use a real card, create a
live charge, or modify the production customer database.

## Configuration exercised

- Dodo environment: test mode
- Product: `DrumToScore — 10 Transcription Credits`
- Product ID: `pdt_0NnK4Qfm2vKzBmmpU4hOO`
- Checkout session: `cks_0NnfdZBAwiKAoNGS0dqtY`
- Synthetic buyer: `dodo-e2e-20260915-1753@example.com`
- Temporary webhook endpoint: `ep_3JNHZOikABdMOflVobIQfinL0Kr`
- Webhook event type: `payment.succeeded`

The API and an isolated SQLite database ran locally. A temporary Cloudflare
quick tunnel exposed only the signed Dodo webhook route. The test used Dodo's
published India success-card simulator and Cashfree's sandbox OTP simulator.
The temporary tunnel, webhook endpoint, and two temporary Dodo API keys were
removed or stopped after the test. No secret value is stored in this record.

## Observed result

| Check | Result |
| --- | --- |
| Initial paid balance | `0` |
| Hosted checkout result | Succeeded in Dodo test mode |
| First signed webhook delivery | HTTP `200`, 716 ms |
| Balance after webhook | `10` |
| Dodo replay of the same event | HTTP `200`, 44 ms |
| Balance after replay | `10` |
| Full-song entitlement after payment | Enabled |

The successful HTTP responses were produced only after the application verified
Dodo's Standard Webhooks signature and validated the purchase, user, checkout
session, product and pack metadata. The unchanged balance after Dodo replay
confirms that the credit grant is idempotent.

## Monitoring follow-up

A least-privilege Sentry personal token named
`DrumToScore GitHub source maps 2026-09-15` was created with `org:read`,
`project:read`, `project:write`, and `project:releases`. Its value was stored as
the GitHub Actions secret `SENTRY_AUTH_TOKEN`; it was never committed.
