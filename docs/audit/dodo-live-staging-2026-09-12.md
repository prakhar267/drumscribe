# Dodo Payments live-staging audit — 12 September 2026

This record contains no API keys, webhook signing secrets, checkout client
secrets, bank details, identity-document data, cookies or card data.

## Verification status

- The owner selected **Individual** and explicitly confirmed submission of the
  product-information attestation.
- Dodo recorded the product information.
- The owner completed the identity and bank steps personally.
- Dodo now displays **LIVE PAYMENTS ACTIVE** and **We're reviewing your
  details**, with a stated review time of up to 72 hours.

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

## Safe staging state

Live credentials are stored as dormant `DRUMSCRIBE_DODO_LIVE_*` values in the
root-owned `0600` Oracle environment file. They are not committed to Git and
were not printed into this record.

The running application remains on the already validated Dodo `test_mode`, and
`NEXT_PUBLIC_BILLING_ENABLED=false`. Therefore the public Buy button is hidden
and no live checkout was created. The live product and webhook are ready, but
the website cannot initiate customer charges in its current configuration.

No actual payment card, real transaction, paid plan or billable infrastructure
action was used while preparing live mode.

## Activation gate

After Dodo's review changes from pending to approved, activation must be an
atomic release: back up the environment file, promote the staged live values to
the active Dodo variables, set the Dodo environment to `live_mode`, restart the
API, confirm readiness, create a no-charge checkout-session smoke test, deploy
the web application with public billing enabled, and monitor the first signed
live webhook. A real payment test is not authorized by this record.
