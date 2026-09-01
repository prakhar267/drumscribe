# Production services

This is the non-secret source of truth for DrumScribe's pre-launch service topology. Credentials live only in the deployment platform, the ignored local `.env`, or macOS Keychain.

## Service map

| Product boundary | Service | App configuration | Current pre-launch status |
| --- | --- | --- | --- |
| PostgreSQL | Neon project `drumstick` (`cool-cell-64604736`), organization `Prakhar` (`org-winter-sea-89158570`), AWS Ohio | `DRUMSCRIBE_DATABASE_URL` | CLI/MCP are configured. All migrations passed first on an ephemeral branch and then on `production`; pooled application connectivity is verified. |
| Durable queue and rate-limit state | Upstash Redis `drumscribe-production`, AWS Ohio | `DRUMSCRIBE_REDIS_URL`; production uses `DRUMSCRIBE_QUEUE_BACKEND=celery` | TLS authentication and write/read/delete verified. Localhost stays `inline` so it remains usable without a separate worker process. |
| Private audio and exports | Neon Object Storage bucket `drumscribe-private`, AWS Ohio | `DRUMSCRIBE_S3_*` | Private bucket, scoped production credential, exact-origin CORS, signed browser upload/download, unsigned denial, streamed move fallback, and cleanup are live-verified. Neon Object Storage is beta, so application retention/deletion remains authoritative. The existing public-read `drumstick` bucket is unused for customer media. |
| Transactional sign-in email | Resend | `DRUMSCRIBE_MAGIC_LINK_DELIVERY=resend`, `DRUMSCRIBE_RESEND_*` | Adapter and unit test are complete; live delivery to the account email passed. Customer delivery is blocked until a custom domain is verified. |
| API error monitoring | Sentry `python-fastapi` | `DRUMSCRIBE_SENTRY_DSN`, `DRUMSCRIBE_SENTRY_TRACES_SAMPLE_RATE` | SDK wiring and a live ingestion event are verified. |
| Web error monitoring | Sentry `drumscribe-web` | `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_DSN`, sample-rate variables | Next.js client, server, edge, global-error, and build integration are complete; lint, type checking, tests, and production build pass. Source-map upload needs a CI auth token at deployment time. |
| Public web | Cloudflare Workers, `drumscribe-web` | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_DEMO_MODE`, `API_ORIGIN` | Vinext production build and live Workers deployment are verified at `https://drumscribe-web.prakhargupta267.workers.dev`. It remains in explicit pre-launch demo mode until the public API URL exists. |
| Public API, worker, and scheduler | Northflank Sandbox | Container environment variables and TLS hostname | Deployment is prepared but blocked on the account owner's GitHub passkey confirmation. Sandbox is suitable for a free pre-launch beta, not an SLA production launch. Oracle is no longer in the selected topology. |
| Logs and uptime | Better Stack | Deployment log drain and public health URLs | Account is connected, but sources and monitors wait for the public API URL. |
| Source and CI | Public GitHub repository `prakhar267/drumscribe` | Repository secrets and workflows | Hosted Actions are enabled on the public repository. Secret scanning, push protection, vulnerability alerts, and Dependabot security updates are enabled; the local parity suite remains required before push. |

## Neon boundary

DrumScribe uses Neon PostgreSQL and Neon Object Storage. Other Neon primitives stay disabled unless they are deliberately adopted:

- Authentication is the application's own first-party magic-link and session implementation, delivered through Resend.
- Private audio and generated exports use the existing S3-compatible boundary backed by the private `drumscribe-private` bucket.
- Neon requires path-style S3 addressing and does not currently expose `CopyObject`; the adapter streams recoverable moves through a temporary local file.
- `DRUMSCRIBE_S3_SERVER_SIDE_ENCRYPTION=auto` omits unsupported AWS SSE request headers for Neon while retaining provider-managed at-rest encryption.
- API and background work run in separate application and worker containers, planned for Northflank during pre-launch.
- The runtime database URL must use Neon's pooled connection string. Alembic migrations must use the direct, unpooled connection string.
- Neon's canonical libpq URL is normalized centrally for SQLAlchemy `asyncpg`: TLS remains required while unsupported libpq-only query parameters are removed before connecting.
- The project-scoped Neon MCP configuration is for development and testing, not a production runtime dependency.
- Create database changes on a temporary Neon branch first, run tests there, and apply them to the default production branch only after review.
- An existing public-read Neon bucket named `drumstick` was observed but is intentionally not wired to customer audio. DrumScribe's storage safety gate requires private S3-compatible storage.

## Secret handling

- `.env` is Git-ignored, mode `0600`, and currently contains only local pre-launch values.
- Local managed-service credentials are also stored in macOS Keychain under DrumScribe-specific service names.
- No committed example contains a real DSN, token, password, or connection string.
- Production secrets must be copied into Northflank/GitHub secret storage rather than committed or baked into images.

## Launch gates that remain external

1. Complete the GitHub passkey confirmation, deploy the API and worker on Northflank, run the migration job, and switch the Worker from demo mode to the generated public API hostname.
2. Verify a customer sending domain in Resend and publish its SPF/DKIM records.
3. Attach Better Stack logs and uptime checks to the deployed health endpoints and document alert recipients.
4. Obtain the commercial provider credentials, contractual approval, retention/training terms, and rights evidence required by the fail-closed production validator. The local Demucs/research path is validated for research only and is never accepted by the production safety gate.
5. Move off Northflank Sandbox to an SLA-capable paid/runtime tier before the production launch.
6. Complete legal-entity/address decisions and qualified review of the customer-facing legal text.
7. Run deployed restore/deletion/security tests and measured quality benchmarks after the public API is available. Local full-stack and rights-cleared recording journeys already pass against production Neon data and storage services.
