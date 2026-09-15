# Launch legal and data checklist

Last audited: 2026-09-15

This is an engineering and product-readiness record, not legal advice. It keeps
confirmed facts separate from founder decisions and items that require qualified
counsel. Do not mark an item complete merely because the website or runtime is
live.

## Founder-supplied business information

| Field | Current value | Status |
| --- | --- | --- |
| Product/service name | DrumToScore | Confirmed product brand |
| Legal operator | Prakhar Gupta, individual sole proprietor using DrumToScore as a trade name | Founder confirmed individual operation; DrumToScore is not described as a separate registered entity |
| Support email | `support@drumtoscore.com` | Active Cloudflare Email Routing rule forwarding to the verified founder Gmail destination |
| Privacy email | `privacy@drumtoscore.com` | Active Cloudflare Email Routing rule forwarding to the verified founder Gmail destination |
| Copyright email | `copyright@drumtoscore.com` | Active Cloudflare Email Routing rule forwarding to the verified founder Gmail destination |
| Security email | `security@drumtoscore.com` | Active Cloudflare Email Routing rule forwarding to the verified founder Gmail destination |
| Address | 25/38 Kaveri Path, Mansarovar, Jaipur, Rajasthan 302020, India | Founder supplied and confirmed for service notices |
| GST status | Currently not GST-registered | Present-status disclosure only; registration obligations must be monitored as turnover, customer locations and law change |
| Launch territory | India and international | Too broad for one generic legal review; prioritize actual sales countries |
| Commercial model | One full song free, then a one-time 10-credit pack for USD 15 | Implemented; production checkout is live |
| Refund approach | Final sale/no change-of-mind refunds, with exceptions for failed delivery, duplicate or unauthorized charges, material defects, merchant rules and mandatory law | Founder supplied “no refund”; narrowed to a legally safer enforceable form |
| Merchant of record | Dodo Payments | Verification complete; live checkout enabled after a no-charge display smoke test |

Do not describe DrumToScore as a company, corporation or separate registered
entity. It is currently a trade name used by the individual operator named above.

## Implemented public disclosures

- `/legal/terms` identifies the individual operator, 18+ eligibility, user-content
  permission, copyright responsibility, accuracy limitations, intended credit
  model, liability baseline, governing law and Jaipur venue.
- `/legal/privacy` describes collected data, purposes, providers, approximate
  technical retention periods, model-training opt-in boundary and user controls.
- `/legal/copyright` gives a usable initial rights-notice route without claiming
  a jurisdiction-specific safe-harbour procedure.
- `/legal/refunds` records the final-sale/no-change-of-mind approach while
  preserving failed-delivery, duplicate/unauthorized-charge, material-defect,
  merchant and mandatory-law remedies.
- Every policy identifies the operator, contact, full address and current
  checkout status.

These are conservative beta policies for the currently live freemium service. They
are not counsel-approved final terms and should not be presented as such.

## Current service-provider data map

| Provider | Purpose and likely data | Recorded location | Current status / open evidence |
| --- | --- | --- | --- |
| Cloudflare | Website delivery, edge proxy, request/network metadata and inbound email routing | Global edge | Free plan active; public DPA and service-subprocessor evidence indexed on 15 September; retain the dashboard/account acceptance record |
| Oracle Cloud | API, private Valkey queue and ML worker; temporarily processes customer audio and project/job requests | Mumbai, India | Always Free host live; public contract/security evidence indexed; Oracle's exact accepted DPA and subprocessor list require the tenancy order and My Oracle Support export |
| Modal | GPU source separation; temporarily receives the uploaded audio and returns a drum stem to the Oracle worker | Asia-Pacific South request route; provider-managed compute locations | Protected endpoint and scale-to-zero L4 active; public DPA/subprocessor evidence indexed; exact deletion/location settings still need account evidence |
| Neon | Managed Auth, account/project database, private audio and exports | AWS Ohio, USA | Live; private bucket, signed links and managed Better Auth verified; public Neon/Databricks DPA and subprocessor evidence indexed; retain the accepted account version and review beta-storage terms |
| Private Valkey | Queue, job coordination and rate-limit state on the Oracle host | Mumbai, India | Not an external processor; Valkey 8 uses append-only persistence, `noeviction`, a private Docker network and no published host port. Upstash is no longer used in production |
| Resend | Account-verification and password-reset email sent through Neon Auth SMTP | Provider-managed | Live and domain verified; public DPA/subprocessor evidence indexed; retain the signed dashboard copy and enforce the 30-day delivery-metadata schedule |
| Sentry | Error and sampled performance telemetry; default PII sending disabled | Provider-managed | Live at 5% trace sampling; public DPA/subprocessor evidence indexed; verify 30-day retention/scrubbing in the dashboard and add the missing GitHub source-map token |
| GitHub | Public source repository, CI and endpoint uptime checks | Provider-managed | Live; uptime checks do not intentionally send customer audio |
| Dodo Payments | Checkout, tax, order, payer and refund data; no uploaded audio | Provider-managed | Verification complete; live checkout enabled; public DPA indexed. The public DPA says the current subprocessor list is available on written request, so that provider response remains to be archived |

The public-source evidence URLs, retrieval hashes and account-specific follow-ups
are recorded in `PROVIDER_DPA_EVIDENCE_2026-09-15.md`. A public URL/checksum is
not a substitute for the exact agreement accepted by this account or for counsel
approving cross-border transfers.

The privacy policy names the current providers, but counsel must select lawful
bases, international-transfer mechanisms, contractual safeguards, retention
periods and any required representatives for actual sales jurisdictions.

## Technical retention configuration

Unless production overrides them, current application defaults are:

| Data | Current behavior |
| --- | --- |
| Session cookie | HTTP-only, secure in production, SameSite=Lax; 30-day maximum |
| Signed media links | About 10 minutes |
| Unprocessed and replaced uploads | Scheduled cleanup after 24 hours |
| Generated export files | Scheduled cleanup after 7 days |
| Inactive anonymous account/project | Scheduled cleanup after 24 hours |
| Deleted signed-in project | Access revoked immediately; 7-day recovery window, then media purge |
| Deleted account | Sessions revoked and email removed immediately; media/exports requested for immediate deletion; opaque audit/tombstone records may remain |
| Active registered project, source audio, transcription and edits | Retained while the project/account exists; deletion follows the rules above |
| Product and ordinary audit events | 12 months, then delete or irreversibly aggregate |
| Authentication/security logs and Sentry events | 30 days by default; preserve only a scoped incident record when required |
| Transactional email delivery metadata | 30 days |
| Ordinary support records | 24 months after closure |
| Privacy-request record | 3 years after closure |
| Payment/refund/tax/chargeback, security-incident and legal-dispute records | Up to 7 years, or the period mandatory law requires |
| Database backup/recovery branch | Maximum 30 days; release-drill branches expire within 24 hours |

The production environment does not override the media/export duration defaults
as of this audit. Storage cleanup is asynchronous and retryable. The hourly
worker enforces object and export lifecycles; database audit/product-event and
operator-held support/email purges require a recorded quarterly review until
automation exists. The 15 September drill verified deletion and recovery paths
without accessing customer objects.

## Model, checkpoint and dataset evidence

| Item | Current evidence | Paid-launch decision |
| --- | --- | --- |
| ADTOF-pytorch code and frame-RNN weights | Code commit and checkpoint SHA-256 pinned; founder attestation says a separate commercial grant exists; underlying grant is not archived in the repository | **Hold** until private grant evidence and recipient legal identity are verified |
| Demucs `htdemucs_ft` | Code is publicly MIT; exact four weights and bag hashes pinned; founder attestation says a separate grant covers inference | **Hold** until the checkpoint/training-rights grant is privately archived and reviewed |
| Beat This `final0` | Upstream states its code and published weights are MIT, while warning that some training files are copyrighted or restrictively licensed; checkpoint SHA-256 is recorded | Archive the exact upstream license/README evidence and obtain counsel review of the stated training-data risk |
| DrumScribe recall-fusion v6 rules | First-party config hash pinned; depends on the three items above and first-party checkpoints | Inherits every upstream evidence requirement |
| Groove MIDI Dataset / E-GMD | Manifests identify CC BY 4.0, version, source and attribution; E-GMD local archive hash is not populated in the reviewed subset manifest | Candidate for commercial training; finish model card and release attribution review |
| MuldjordKit samples | Local CC BY 4.0 license retained; first-party model manifest records use | Candidate for commercial training; publish required attribution with the model/service notices |
| FreePats World Percussion | Local CC0 1.0 text retained | Candidate for commercial training; preserve source and artifact lineage |
| RWC, MDB and other research evaluation material | Repository benchmark records identify non-commercial/research restrictions | Never train or calibrate a paid production artifact on these sources unless a separate grant is obtained |
| Customer audio/corrections | Model-improvement toggle is off by default; no training grant by default | Never train without explicit consent, lawful-basis review and a separately governed dataset admission process |
| YourMT3+, OaF downloaded weights and other research backends | Code/checkpoint/data rights remain incomplete or incompatible in the engineering register | Excluded from production |

The exact hashes and component-by-component notes remain in
`MODEL_LICENSING.md` and `COMMERCIAL_MODEL_RIGHTS_APPROVAL.md`. Preserve the old
benchmark records as historical audit evidence even where their brand name or
conclusions have since changed.

## Required founder and counsel decisions before paid launch

1. Privately archive the original model-rights grants and have counsel confirm
   that the grant recipient matches the operator and covers paid hosted use,
   cloud copies, territories and exact checkpoint hashes.
2. Obtain qualified review of governing law, dispute venue, age requirement,
   warranty/limitation of liability, suspension/appeal and jurisdiction-specific
   consumer provisions before expanding paid sales internationally.
3. Monitor the first genuine Dodo purchase for a signed HTTP `200` webhook and
   an exactly-once 10-credit grant. The live checkout display was verified
   without making a real purchase before enabling the public Buy button.
4. Automate the adopted 12-month database-event purge and record the quarterly
   mailbox/support deletion review. The retention periods themselves are now set
   in `DATA_RETENTION.md`.
5. Download the exact account-accepted provider DPAs and restricted subprocessor
   evidence identified in `PROVIDER_DPA_EVIDENCE_2026-09-15.md`, then have
   counsel approve cross-border transfer mechanisms for prioritized launch countries.
6. Operate and periodically rehearse
   `docs/operations/SUPPORT_AND_INCIDENT_PROCEDURE.md`, which now records the
   request routes, response owner, internal targets and incident workflow.
7. Monitor GST registration obligations; the present “not GST-registered” status
   is not a permanent exemption determination.

If any onboarding step asks for a payment card, paid plan or charge, stop and
obtain the founder's explicit permission. No card use is authorized by this
checklist.
