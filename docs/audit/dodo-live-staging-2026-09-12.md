# Dodo Payments live-staging audit — 12 September 2026

This record contains no API keys, webhook signing secrets, checkout client
secrets, bank details, identity-document data, cookies or card data.

## Verification status

- The owner selected **Individual** and explicitly confirmed submission of the
  product-information attestation.
- Dodo recorded the product information.
- The owner completed the identity and bank steps personally.
- On 14 September 2026, Dodo displayed **Live payments are active**, **You can
  now receive and pay out**, and **Verification is complete**.

## Live resources prepared

| Item | Non-secret value |
| --- | --- |
| Offer | One-time pack of 10 full-song transcription credits for USD 15 |
| Dodo live product | `pdt_0NnRiuxjDHzzyeOdCfwnX` |
| Webhook URL | `https://drumtoscore.com/api/v1/billing/webhooks/dodo` |
| Dodo live endpoint | `ep_3JEOk86IGLEV3iMQxHklxplZxdo` |
| Subscribed events | `payment.succeeded`, `refund.succeeded` |
| Live API credential | `DrumToScore production API v2`, read/write |

The live product was imported from the validated test-mode product. A read-only
request from the Oracle host authenticated with the staged live credential,
returned HTTP `200`, and matched the live product ID. An earlier one-time key
whose copy was not retained was deleted; only the replacement key remains.

## Activation record — 14 September 2026

Live credentials are stored as dormant `DRUMSCRIBE_DODO_LIVE_*` values in the
root-owned `0600` Oracle environment file. They are not committed to Git and
were not printed into this record.

Immediately before activation, Neon branch `billing-live-pre-20260914`
(`br-green-band-a5ctyvhy`) was created from the production branch as a
time-limited database restore point. The activation utility made root-only
backup `/etc/drumscribe/drumscribe.env.pre-dodo-live-20260914T085449Z`, then
atomically promoted the staged values. The running API now uses Dodo
`live_mode`, the live product and the live signing key.

The live product and webhook endpoint each returned HTTP `200`. A production
checkout-session request returned HTTP `201`, produced an HTTPS `dodo.pe`
checkout URL, and the hosted page displayed DrumToScore's 10-credit, USD 15
offer. The temporary smoke-test account was deleted. An invalid-signature
webhook was rejected with HTTP `401`.

Cloudflare Worker version `03a3fb2c-9ec2-4bac-aaa6-17fae9baba6a` was deployed
with public billing enabled. The live pricing page now shows **Sign in to buy
credits** to a signed-out visitor and routes that action to the production
magic-link sign-in page.

No actual payment card, real transaction, paid plan or billable infrastructure
action was used while staging, activating or testing live mode.

## Remaining live verification

No live `payment.succeeded` event was generated because that requires a real
purchase. The first genuine customer purchase must be monitored for a signed
HTTP `200` webhook response and one exactly-once 10-credit grant. The earlier
test-mode flow already proved signed success, duplicate-event idempotency,
credit reservation/return and refund handling. A real card test remains outside
this record's authorization.
