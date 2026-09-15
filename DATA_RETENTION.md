# Data retention

Policy adopted: 15 September 2026

This is the engineering retention contract for the current individual operator.
Provider contracts and qualified legal review may require shorter periods. A
duration below is a maximum, not a reason to keep data that is no longer needed.
Where the application does not yet automate a database or mailbox purge, the
operator must complete and record the deletion during the quarterly review.

| Data | Default | Access removal | Physical purge |
|---|---:|---|---|
| Anonymous project/media | 24 hours | At expiry or user deletion | Hourly retention task |
| Unprocessed/replaced upload | 24 hours | Immediately when replaced/rejected | Hourly retention task |
| Generated export | 7 days | At expiry/deletion | Hourly retention task |
| Active registered project, source audio, transcription, edits and revisions | Until the owner deletes the project/account or the service is terminated | User-controlled deletion or service termination | Media follows the deletion rules below; project records are removed or irreversibly de-identified during the next quarterly database review unless a legal hold applies |
| Recoverable project deletion | 7 days | Immediately | After grace period |
| Permanent account deletion | No grace | Immediately | Immediate attempt, then idempotent retention retry |
| Signed media/export URL | 10 minutes | Expiry; new URLs refused after deletion | Object follows its lifecycle |
| Neon Auth account and session data | Account lifetime; sessions expire or are revoked according to the deployed Neon Auth policy | Sign-out, revocation, account deletion or expiry | Neon Auth/provider cleanup plus local account deletion workflow |
| Verification or password-reset link | Provider-configured short lifetime and single purpose | Consumption/expiry | Provider cleanup policy; raw tokens are not copied into product records |
| Free-song abuse-prevention claim | While the one-free-song offer operates | Detached from deleted account | Keyed HMAC identity and used timestamp only; no email is retained in the claim |
| Product events and ordinary application audit events | 12 months | Restricted operational access | Delete or irreversibly aggregate during the quarterly review |
| Authentication/security logs and Sentry events | 30 days by default | Restricted operational access | Provider/application expiry; preserve a minimal incident record only when needed |
| Transactional email delivery metadata | 30 days | Restricted support access | Provider/dashboard deletion or expiry; do not retain message bodies in support records |
| Ordinary support records | 24 months after closure | Restricted operator access | Delete during the quarterly review |
| Privacy-request record | 3 years after closure | Restricted operator access | Delete or de-identify after the period unless law requires longer |
| Payment, refund, tax, chargeback, security-incident or legal-dispute record | Up to 7 years after closure/transaction, or the shorter/longer period mandatory law requires | Restricted operator access | Scheduled legal-record review; uploaded audio is never retained in these records |
| Database backup or recovery branch | Maximum 30 days; short-lived drills expire within 24 hours | Never exposed to users | Replay deletion markers before use, then destroy the drill environment |
| Provider copy | Contract-specific | Provider API/contract-specific | Record `retentionExpiresAt` per model run |

Object keys are opaque and private. Soft deletion immediately blocks application
authorization and marks objects for deletion. The hourly Celery Beat task performs
idempotent storage deletion and durable database state changes. Alert when it has
not succeeded for two hours.

Customer uploads and corrections are excluded from model training by default.
`allowModelImprovement` is opt-in only; it is not by itself a completed legal,
licensing or dataset-approval workflow. Provider training/retention must be
disabled contractually or technically where available and documented before use.

Backups need a documented deletion window. Restoring a backup must replay deletion
markers before the environment is exposed. Logs, Sentry events and support records
must not contain media, signed URLs, auth tokens, API keys or full filenames.

The hourly worker currently enforces object/media and export lifecycles. The
12-month audit/product-event purge and operator-held email/support schedule are
adopted policy but require a recorded quarterly review until automated deletion
is implemented. Legal holds must be documented, scoped to the minimum records,
reviewed at least every 90 days and must never be used to retain customer audio
unnecessarily.
