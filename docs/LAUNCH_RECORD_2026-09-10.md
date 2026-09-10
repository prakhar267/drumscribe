# DrumToScore launch execution record — 10 September 2026

This is the non-secret handoff record for the production-readiness work performed
on 10 September 2026. It intentionally excludes passwords, API keys, webhook
secrets, database URLs, storage credentials, card data, cookies and sign-in links.

## Founder constraints and supplied business data

| Item | Recorded value or rule |
| --- | --- |
| Product brand | DrumToScore |
| Domain | `drumtoscore.com` |
| Founder/operator contact supplied earlier | Prakhar Gupta |
| Address supplied earlier | 25/38 Kaveri Path, Mansarovar, Jaipur, Rajasthan, India |
| Launch territory | India and international |
| Offer | One free complete-song transcription, then a one-time 10-credit pack intended at approximately USD 15 |
| Payment safety rule | No payment card may be entered, selected, charged or authorized. Stop if any provider requests a card or paid plan. |

The registered legal operator name, entity type, postal code and tax/GST status
have not been confirmed. Earlier notes used the business name “DrumScribe” while
the product now uses DrumToScore; this must be resolved before paid launch.

## External configuration completed

### Domain and Cloudflare

- `drumtoscore.com` remains registered at Namecheap and delegated to Cloudflare
  nameservers. Domain privacy/protection was observed as active.
- The existing production Worker routes, canonical-host redirect, TLS settings,
  API proxy, security headers and Resend records were preserved.
- Cloudflare HSTS was enabled for 12 months with subdomains included, preload
  off and no-sniff on. The public homepage now returns
  `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
- Cloudflare Email Routing was enabled on the free plan.
- Six obsolete Namecheap Email Forwarding DNS records were removed because they
  conflicted with Cloudflare Email Routing: five apex `eforward*.registrar-servers.com`
  MX records and the matching apex Namecheap forwarding SPF record.
- Cloudflare's three apex inbound MX records and inbound SPF record were added by
  the Email Routing activation flow.
- The existing Resend sending-domain MX, SPF, DKIM and DMARC records were not
  removed.
- The founder Gmail destination was already verified by Cloudflare.
- Four active routing rules were created:

  | Public address | Destination |
  | --- | --- |
  | `support@drumtoscore.com` | Verified founder Gmail destination |
  | `privacy@drumtoscore.com` | Verified founder Gmail destination |
  | `copyright@drumtoscore.com` | Verified founder Gmail destination |
  | `security@drumtoscore.com` | Verified founder Gmail destination |

- A production DrumToScore magic-link email was addressed to
  `support@drumtoscore.com` and was observed in the destination Gmail inbox,
  proving the inbound forwarding route. The one-time link itself is not recorded.
- Public DNS was independently checked: Cloudflare's three MX targets and inbound
  SPF were present; DMARC and the Resend DKIM record remained present.

No Cloudflare paid email-sending product, Workers paid plan or card was used.
Outbound application sign-in email continues to use the previously configured
Resend service.

### Dodo Payments

The non-financial onboarding profile was prepared with:

- full name: Prakhar Gupta;
- business/product name: DrumToScore;
- website: `drumtoscore.com`;
- category: SaaS/AI or digital products;
- country: India; and
- use-case description: one free AI drum transcription, followed by pay-as-you-go
  transcription credits with a merchant of record.

The Dodo test-mode integration is now configured end to end:

- test product `pdt_0NnK4Qfm2vKzBmmpU4hOO` represents a one-time USD 15 pack
  of 10 full-song transcription credits;
- webhook endpoint `ep_3J9V7vBTD1QrDXAhA40KOPCmqzk` sends only
  `payment.succeeded` and `refund.succeeded` to the production API;
- the API is explicitly configured for Dodo `test_mode`; and
- API and endpoint-specific webhook credentials are secret, uncommitted and
  stored in the root-owned `0600` production environment file.

A complete sandbox checkout succeeded using only Dodo's published test card.
The signed webhook returned HTTP 200, changed the matching Neon purchase to
`PAID`, and granted exactly 10 credits. Replaying the same event returned HTTP
200 without increasing the balance beyond 10. The three exact synthetic test
accounts were deleted afterward. No actual card or real-money transaction was
used. Full evidence is in
`docs/audit/dodo-test-mode-2026-09-11.md`.

Dodo still shows **Product Information Form Pending**. Production billing and
the public Buy button remain disabled until merchant verification and live-mode
configuration are complete.

### Neon

- CLI access was verified for organization `Prakhar`
  (`org-winter-sea-89158570`) and project `drumstick`
  (`cool-cell-64604736`).
- The organization reports plan `free`.
- The project is PostgreSQL 18 in `aws-us-east-2` and its primary branch is
  `production`.
- Application database connections remain pooled; migration and restore work use
  a direct connection as required by the Neon runbook.
- Migration `9f4b8d16a2c7` was first verified on a disposable release branch,
  applied to `production`, and confirmed as the production Alembic head. The
  release branch was deleted after the successful deployment; only `production`
  remains.
- Customer media continues to use the private `drumscribe-private` Neon Object
  Storage bucket. No storage upgrade or card was used.

### Existing production topology retained

| Boundary | Current service |
| --- | --- |
| Public website/edge | Cloudflare Worker `drumscribe-web` |
| Public API and CPU transcription worker | Oracle Cloud Always Free Ampere A1 in Mumbai |
| Database and private object storage | Neon project `drumstick` |
| Queue and distributed rate-limit state | Upstash Redis |
| Passwordless sign-in delivery | Resend |
| Error/performance telemetry | Sentry |
| Source, CI and uptime probes | Public GitHub repository and GitHub Actions |
| Merchant of record | Dodo integration implemented; external onboarding incomplete and checkout disabled |

Production secrets remain only in ignored local configuration/keychain or the
root-owned `0600` environment file on the Oracle host. No secret was added to
this record or Git.

## Product and code hardening completed

### Freemium and billing integrity

- Added a durable pseudonymous one-free-song claim.
- Gmail/Googlemail dot and plus aliases share the same free entitlement.
- Deleting and recreating an account no longer resets a used free song.
- Added an idempotent production backfill for accounts created before the claim.
- Ran that backfill after deployment; durable claims were established for all 10
  existing accounts without consuming a transcription credit.
- Serialized checkout creation for a user/idempotency key.
- Tied each paid job to the purchase pack that funded it.
- Failed or cancelled paid jobs restore the credit to the correct pack.
- Added signed, idempotent `refund.succeeded` handling.
- A full refund revokes only unused credits from the relevant purchase.
- Partial refunds fail closed for manual reconciliation.
- Replayed or stale payment/refund events cannot grant or revoke twice.
- Tightened webhook checks for the configured product, quantity, pack metadata,
  purchase, user, checkout session, payment ID and signature.
- No application table stores card number, CVV or payout-bank credentials.

Billing activation details are in `docs/BILLING_LAUNCH_RUNBOOK.md`.

### Legal, privacy and contact surfaces

- Expanded the public Terms, Privacy and Copyright/upload policies.
- Added a public Refund policy and linked it from the legal navigation/footer.
- Added the public support email to the footer.
- Added a private vulnerability-reporting address and coordinated-disclosure
  guidance to `SECURITY.md`.
- Added a provider/data-location map, retention inventory and launch legal checklist.
- Corrected licensing records so an internal founder approval is not presented as
  independent evidence of an upstream commercial-use grant.

These pages are transparent beta policies, not a substitute for qualified legal
review. Paid launch remains gated on the operator details and legal decisions in
`docs/legal/LAUNCH_LEGAL_AND_DATA_CHECKLIST.md`.

### Operational safety

- Neon snapshot parity and a separate PostgreSQL 18 dump/restore with a synthetic
  canary passed without exporting row contents.
- The exact 16-table source/restore row-count and normalized-schema fingerprints
  matched. The restored Alembic revision was `9f4b8d16a2c7`.
- Both disposable Neon drill branches and the synthetic restore database were
  deleted after verification; only `production` remains.
- Account-deletion tests now prove session revocation, identity removal, project
  inaccessibility, physical private-audio removal and signed-URL invalidation.
- The live Oracle host and public edge were audited read-only. All nine public
  HTTPS, redirect, header, HSTS, CORS, authorization, readiness and certificate
  checks pass.
- The complete evidence and non-secret hashes are in
  `docs/audit/production-operations-2026-09-10.md`.

No production customer record, object or account was changed or deleted by the
drills.

### Dependency hygiene

- Removed the obsolete nested `apps/web/pnpm-lock.yaml`. It was not used by the
  root pnpm workspace but still pinned a vulnerable development-only `sharp`
  release and caused a GitHub high-severity alert.
- The canonical root lockfile enforces patched `sharp` `0.35.4` throughout the
  workspace. Frozen installation, the web production build and the high-severity
  pnpm audit pass with no known vulnerabilities.

## Verification evidence

| Check | Result |
| --- | --- |
| Web lint | Passed |
| Web TypeScript | Passed |
| Web unit/component tests | 25 passed |
| Next.js production build | Passed; all four legal routes generated |
| API Ruff format/check | Passed |
| API mypy | Passed |
| API tests | 83 passed, 1 skipped |
| Support email forwarding | Passed end to end |
| Public inbound DNS | Passed |
| Backup/restore and deletion rehearsal | Passed |
| Live edge/security audit | 9 of 9 passed |
| Full integrated local release gate, including dependency audits | Passed; no known dependency vulnerabilities found |
| Neon branch-first migration check | Passed on disposable release branch |
| Production database migration | Passed; `9f4b8d16a2c7` is the live head |
| Oracle production deployment | Passed; API, ML worker, scheduler and proxy healthy |
| Cloudflare web deployment | Passed; Worker version `48a775ec-bc21-431f-9425-458b146f111f` |
| Public route smoke test | Passed; homepage, pricing, demo, API readiness and all four legal pages returned HTTP 200 |
| Production free-claim backfill | Passed; 10 existing accounts processed |
| Dodo sandbox checkout and signed webhook | Passed; 10 credits granted exactly once and duplicate replay remained at 10 |
| Hosted GitHub CI | Passed for release commit: [run 34411777668](https://github.com/prakhar267/drumscribe/actions/runs/34411777668) |
| Hosted production uptime probe | Passed after release: [run 34412600218](https://github.com/prakhar267/drumscribe/actions/runs/34412600218) |

Release source commit `c81839472ffce2db98d43faeaa8c3a9335fe9021` is pushed to
the public GitHub repository and deployed. The final public security audit ran at
`2026-09-09T22:39:24Z` and passed all 9 checks, including live database, queue,
private storage and provider readiness.

## Explicit remaining blockers

1. The owner must personally complete Dodo's pending product-information,
   legal/tax/identity and payout-bank verification. Stop if Dodo requests a card
   or paid plan.
2. After Dodo approval, create separate live credentials, product and webhook;
   run an explicitly authorized live-mode smoke transaction; then enable the
   public checkout. Test and live Dodo data must remain isolated.
3. Privately archive the actual grants for the exact Demucs and ADTOF code/weights
   and have qualified counsel verify paid hosted commercial use. The public Demucs
   code license does not cover its pretrained weights, and the pinned ADTOF-pytorch
   tree does not contain a clear root license grant.
4. Confirm the legal operator/entity name, postal code, tax/GST position, governing
   law, age eligibility, liability/dispute provisions, final refund window and
   international consumer/privacy terms.
5. Review provider DPAs, subprocessors, cross-border transfer terms and support/
   audit retention periods.
6. Approve a paid capacity plan before promising an SLA or accepting traffic that
   exceeds the single free Oracle worker. No paid scaling is authorized now.

## No-actual-card and no-paid-action ledger

- Only Dodo's published Test Mode card number was submitted for the sandbox
  checkout. No actual payment card number was viewed, copied, entered, selected
  or submitted.
- No charge, purchase, paid plan, trial requiring a card or billable resource was
  authorized.
- Dodo merchant terms were not accepted on the founder's behalf.
- Checkout is disabled in production.
- Neon was verified as the free plan.
- Cloudflare Email Routing was configured as a free inbound service.
- Existing Namecheap auto-renew settings were observed but not changed or invoked;
  no renewal purchase was made.
