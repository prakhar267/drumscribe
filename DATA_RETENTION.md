# Data retention

This is the engineering retention contract; provider contracts and legal review
may require shorter periods. Production values are configurable and must be
recorded per environment.

| Data | Default | Access removal | Physical purge |
|---|---:|---|---|
| Anonymous project/media | 24 hours | At expiry or user deletion | Hourly retention task |
| Unprocessed/replaced upload | 24 hours | Immediately when replaced/rejected | Hourly retention task |
| Generated export | 7 days | At expiry/deletion | Hourly retention task |
| Recoverable project deletion | 7 days | Immediately | After grace period |
| Permanent account deletion | No grace | Immediately | Immediate attempt, then idempotent retention retry |
| Signed media/export URL | 10 minutes | Expiry; new URLs refused after deletion | Object follows its lifecycle |
| Session | 30 days | Revocation, account deletion or expiry | Database cleanup policy |
| Magic link | 15 minutes, single use | Consumption/expiry | Database cleanup policy |
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
