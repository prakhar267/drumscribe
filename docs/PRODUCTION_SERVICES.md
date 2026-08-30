# Production services

This is the non-secret source of truth for DrumScribe's pre-launch service topology. Credentials live only in the deployment platform, the ignored local `.env`, or macOS Keychain.

## Service map

| Product boundary | Service | App configuration | Current pre-launch status |
| --- | --- | --- | --- |
| PostgreSQL | Neon project `drumstick` (`cool-cell-64604736`), organization `Prakhar` (`org-winter-sea-89158570`), AWS Ohio | `DRUMSCRIBE_DATABASE_URL` | Project and production branch verified. CLI OAuth, environment pull, migration, and application connectivity still require final authorization. |
| Durable queue and rate-limit state | Upstash Redis `drumscribe-production`, AWS Ohio | `DRUMSCRIBE_REDIS_URL`; production uses `DRUMSCRIBE_QUEUE_BACKEND=celery` | TLS authentication and write/read/delete verified. Localhost stays `inline` so it remains usable without a separate worker process. |
| Private audio and exports | Cloudflare R2 private bucket | `DRUMSCRIBE_S3_*` | Account is connected. The bucket and narrowly scoped S3 credentials are pending refreshed R2 authorization. |
| Transactional sign-in email | Resend | `DRUMSCRIBE_MAGIC_LINK_DELIVERY=resend`, `DRUMSCRIBE_RESEND_*` | Adapter and unit test are complete; live delivery to the account email passed. Customer delivery is blocked until a custom domain is verified. |
| API error monitoring | Sentry `python-fastapi` | `DRUMSCRIBE_SENTRY_DSN`, `DRUMSCRIBE_SENTRY_TRACES_SAMPLE_RATE` | SDK wiring and a live ingestion event are verified. |
| Web error monitoring | Sentry `drumscribe-web` | `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_DSN`, sample-rate variables | Next.js client, server, edge, global-error, and build integration are complete; lint, type checking, tests, and production build pass. Source-map upload needs a CI auth token at deployment time. |
| Public web, API, worker, and beat | Oracle Cloud | Container environment variables and TLS hostnames | Account provisioning is external and still pending. No production workload is deployed yet. |
| Logs and uptime | Better Stack | Deployment log drain and public health URLs | Account is connected, but sources and monitors wait for the public Oracle URLs. |
| Source and CI | GitHub `prakhar267/drumscribe` | Repository secrets and workflows | CLI access is working. Hosted Actions billing/spending availability remains a launch check. |

## Neon boundary

DrumScribe currently uses Neon only for PostgreSQL. Do not enable Neon Auth, Storage, Functions, or AI features merely because they are available:

- Authentication is the application's own first-party magic-link and session implementation, delivered through Resend.
- Private audio and generated exports use the existing S3-compatible storage boundary, planned for Cloudflare R2.
- API and background inference run in application and worker containers, planned for Oracle Cloud.
- The runtime database URL must use Neon's pooled connection string. Alembic migrations must use the direct, unpooled connection string.
- The project-scoped Neon MCP configuration is for development and testing, not a production runtime dependency.
- Create database changes on a temporary Neon branch first, run tests there, and apply them to the default production branch only after review.

## Secret handling

- `.env` is Git-ignored, mode `0600`, and currently contains only local pre-launch values.
- Local managed-service credentials are also stored in macOS Keychain under DrumScribe-specific service names.
- No committed example contains a real DSN, token, password, or connection string.
- Production secrets must be copied into Oracle/GitHub secret storage rather than committed or baked into images.

## Launch gates that remain external

1. Authorize the Neon CLI, link the exact project, pull pooled/direct URLs, migrate with the direct URL, and run connectivity tests with the pooled URL.
2. Create the private R2 bucket, block public access, configure exact-origin CORS, and issue bucket-scoped credentials.
3. Finish Oracle provisioning; deploy separate web, API, worker, and single beat services behind TLS.
4. Verify a customer sending domain in Resend and publish its SPF/DKIM records.
5. Attach Better Stack logs and uptime checks to the deployed health endpoints and document alert recipients.
6. Obtain the commercial provider credentials, contractual approval, retention/training terms, and rights evidence required by the fail-closed production validator.
7. Complete legal-entity/address decisions and qualified review of the customer-facing legal text.
8. Run staging migrations from zero, restore/deletion/security tests, real browser acceptance, and measured quality benchmarks before launch.
