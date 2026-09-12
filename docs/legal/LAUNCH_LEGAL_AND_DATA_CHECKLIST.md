# Launch legal and data checklist

Last audited: 2026-09-12

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
| Commercial model | One full song free, then a one-time 10-credit pack intended at about USD 15 | Implemented; production checkout remains disabled |
| Refund approach | Final sale/no change-of-mind refunds, with exceptions for failed delivery, duplicate or unauthorized charges, material defects, merchant rules and mandatory law | Founder supplied “no refund”; narrowed to a legally safer enforceable form |
| Merchant of record | Dodo Payments | Sandbox verified; live product, credential and webhook staged; review pending and public checkout disabled |

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

These are conservative beta policies for the currently live free service. They
are not counsel-approved final terms and should not be presented as such.

## Current service-provider data map

| Provider | Purpose and likely data | Recorded location | Current status / open evidence |
| --- | --- | --- | --- |
| Cloudflare | Website delivery, edge proxy, request/network metadata | Global edge | Free plan active; obtain/retain applicable DPA and subprocessor list |
| Oracle Cloud | API and ML worker; temporarily processes customer audio and project/job requests | Mumbai, India | Always Free host live; record tenancy terms, security ownership and deletion procedure |
| Neon | Account/project database plus private audio and exports | AWS Ohio, USA | Live; private bucket and signed links verified; beta-storage terms and DPA need review |
| Upstash | Queue, job coordination and rate-limit state | AWS Ohio, USA | Live; confirm persistence, retention and DPA settings |
| Resend | Account email and one-time sign-in messages | Provider-managed | Live and domain verified; retain DPA/subprocessor/retention terms |
| Sentry | Error and sampled performance telemetry; default PII sending disabled | Provider-managed | Live at 5% trace sampling; document retention, scrubbing and access settings |
| GitHub | Public source repository, CI and endpoint uptime checks | Provider-managed | Live; uptime checks do not intentionally send customer audio |
| Dodo Payments | Checkout, tax, order, payer and refund data after activation; no uploaded audio | Provider-managed | Sandbox verified; live resources staged; review pending and public checkout disabled |

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
| Product/audit records | No complete production retention schedule is configured; counsel and operations must set one |

The production environment does not override the listed duration defaults as of
this audit. Storage cleanup is asynchronous and retryable, so an operational
deletion drill must verify actual completion.

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
3. Wait for Dodo's live review to complete, then verify the live checkout display
   without making a real purchase before enabling the public Buy button.
4. Set a defensible retention schedule for database, product, audit, support,
   email, queue and Sentry records; run deletion and restore drills.
5. Retain provider DPAs/subprocessor lists and approve cross-border transfer
   mechanisms for prioritized launch countries.
6. Operate and periodically rehearse
   `docs/operations/SUPPORT_AND_INCIDENT_PROCEDURE.md`, which now records the
   request routes, response owner, internal targets and incident workflow.
7. Monitor GST registration obligations; the present “not GST-registered” status
   is not a permanent exemption determination.

If any onboarding step asks for a payment card, paid plan or charge, stop and
obtain the founder's explicit permission. No card use is authorized by this
checklist.
