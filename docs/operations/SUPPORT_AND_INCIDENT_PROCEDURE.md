# DrumToScore support and incident procedure

Last reviewed: 12 September 2026

This is the operating procedure for the current individual business. It sets
internal response targets, not a contractual service-level agreement.

## Owner and monitored routes

Prakhar Gupta is the individual operator and response owner. Cloudflare Email
Routing forwards these domain addresses to the founder's verified mailbox:

| Address | Use | Internal first-response target |
| --- | --- | --- |
| `support@drumtoscore.com` | Product, account and billing help | Two business days |
| `privacy@drumtoscore.com` | Access, correction and deletion requests | Acknowledge within two business days; complete within the period required by applicable law |
| `copyright@drumtoscore.com` | Rights-holder notices and counter-notices | Two business days |
| `security@drumtoscore.com` | Vulnerability reports and suspected incidents | One business day; immediately for credible active compromise |

The owner must check the destination mailbox and spam folder at least once each
business day. Never request or retain a complete card number, CVV, password,
magic link, API key or private audio by ordinary email.

## Intake record

For every material request, record the received time, channel, category, account
identifier or Dodo order reference when applicable, evidence, action owner,
deadline, decision, completion time and any data deleted or disclosed. Keep the
minimum information necessary and do not copy customer audio into the record.

Identity must be verified before disclosing account data or carrying out a
privacy request. Billing investigations should use the Dodo order reference and
account email; card data remains with Dodo Payments.

## Incident severity and response

| Severity | Example | Initial action |
| --- | --- | --- |
| Critical | Confirmed customer-data exposure, active account takeover, signing-key compromise | Restrict the affected path, preserve minimal evidence, rotate compromised credentials, contact affected providers and begin legal notification assessment immediately |
| High | Production unavailable, payment credits granted incorrectly, private object exposed by a valid URL to the wrong user | Disable the affected feature, stop new admissions if needed, identify scope and begin recovery |
| Medium | Repeated job failures, delayed email, degraded transcription or export | Limit queue growth, communicate the degraded feature and repair or roll back |
| Low | Isolated UI defect or non-blocking support question | Triage into the normal product queue |

Use Sentry for application failures and GitHub Actions for CI and public endpoint
checks. The Oracle API readiness endpoint covers database, queue, private object
storage and model-provider availability. GitHub's scheduled workflow is
best-effort and does not create a guaranteed detection time.

## Billing and refund handling

Dodo Payments is the merchant of record. Public live checkout stays disabled
until Dodo's review is complete. When enabled, send duplicate, unauthorized,
failed-delivery and approved refund cases through Dodo and reconcile the signed
webhook result with the matching purchase and credit pack. Do not manually grant
credits from an email alone.

The published policy is final sale/no change of mind, subject to paid credits not
being delivered, duplicate or unauthorized charges, material defects that cannot
be corrected, Dodo rules and mandatory law. A failed or cancelled transcription
returns its reserved credit automatically and is not itself a payment refund.

## Recovery and closure

Before closing an incident, verify readiness, the customer-visible workflow,
credit and purchase reconciliation when relevant, cleanup of temporary objects,
and any required credential rotation. Record the root cause, timeline, customer
impact, fix, preventive action and evidence links without including secrets.

Do not promise an uptime or processing-time SLA while the free production tier
uses one API host and one worker. Capacity thresholds and paid scaling require an
explicit founder decision before any card, paid plan or charge is used.
