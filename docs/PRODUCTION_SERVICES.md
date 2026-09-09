# Production services

This is the non-secret source of truth for DrumToScore's pre-launch service topology. Credentials live only in the deployment platform, the ignored local `.env`, or macOS Keychain.

## Service map

| Product boundary | Service | App configuration | Current pre-launch status |
| --- | --- | --- | --- |
| PostgreSQL | Neon project `drumstick` (`cool-cell-64604736`), organization `Prakhar` (`org-winter-sea-89158570`), AWS Ohio | `DRUMSCRIBE_DATABASE_URL` | CLI/MCP are configured. All migrations passed first on an ephemeral branch and then on `production`; pooled application connectivity is verified. |
| Durable queue and rate-limit state | Upstash Redis `drumscribe-production`, AWS Ohio | `DRUMSCRIBE_REDIS_URL`; production uses `DRUMSCRIBE_QUEUE_BACKEND=celery` | TLS authentication and write/read/delete verified. Localhost stays `inline` so it remains usable without a separate worker process. |
| Private audio and exports | Neon Object Storage bucket `drumscribe-private`, AWS Ohio | `DRUMSCRIBE_S3_*` | Private bucket, scoped production credential, exact-origin CORS, signed browser upload/download, unsigned denial, streamed move fallback, and cleanup are live-verified. The production API keeps CORS aligned with `https://drumtoscore.com`, `https://www.drumtoscore.com`, and the fallback Workers URL. Neon Object Storage is beta, so application retention/deletion remains authoritative. The existing public-read `drumstick` bucket is unused for customer media. |
| Transactional sign-in email | Resend | `DRUMSCRIBE_MAGIC_LINK_DELIVERY=resend`, `DRUMSCRIBE_RESEND_*` | Adapter and unit test are complete. `drumtoscore.com` has DKIM, SPF, and DMARC records published through Cloudflare; Resend verification was requested on 10 September 2026. |
| Merchant of record and credits | Dodo Payments | `DRUMSCRIBE_BILLING_*`, `DRUMSCRIBE_DODO_*`, `NEXT_PUBLIC_BILLING_ENABLED` | One free complete song, paid-credit reservation/refund, server-created checkout, signed idempotent webhook fulfillment, pricing, and success UX are implemented and tested. Checkout remains disabled until a Dodo test product, API key, and webhook signing key are supplied and the account owner completes onboarding. |
| API error monitoring | Sentry `python-fastapi` | `DRUMSCRIBE_SENTRY_DSN`, `DRUMSCRIBE_SENTRY_TRACES_SAMPLE_RATE` | SDK wiring and a live ingestion event are verified. |
| Web error monitoring | Sentry `drumscribe-web` | `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_DSN`, sample-rate variables | Next.js client, server, edge, global-error, and build integration are complete; lint, type checking, tests, and production build pass. Source-map upload needs a CI auth token at deployment time. |
| Public web | Cloudflare Workers, `drumscribe-web` | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_DEMO_MODE`, `API_ORIGIN` | Production mode is live at `https://drumtoscore.com`; `www` redirects to the canonical host with its path and query intact. Cloudflare enforces HTTPS, TLS 1.2+, and the verified response-security headers. Both Workers routes and the same-origin `/api/v1/*` proxy are verified; the Workers URL remains a fallback. |
| Public API, worker, and scheduler | Oracle Cloud Always Free Ampere A1, Mumbai | Root-only environment file, Docker Compose, Caddy TLS | `drumscribe-production` is live on 1 OCPU/6 GB with a 46.6 GB boot volume. API readiness, Celery worker, Celery Beat, model-bundle verification, Redis TLS, firewalling, and public HTTPS are verified. No load balancer, NAT gateway, reserved IP, paid plan, or card action was used. |
| Logs and uptime | GitHub Actions scheduled probe plus Sentry | `PUBLIC_WEB_URL`, `PUBLIC_API_HEALTH_URL`, and the Sentry variables above | The canonical public web and proxied API readiness endpoint are configured as repository variables and checked every 15 minutes by `.github/workflows/uptime.yml`; failed runs use the repository owner's GitHub Actions notification settings. Better Stack remains optional. |
| Source and CI | Public GitHub repository `prakhar267/drumscribe` | Repository secrets and workflows | Hosted Actions are enabled on the public repository. Secret scanning, push protection, vulnerability alerts, and Dependabot security updates are enabled; the local parity suite remains required before push. |

## Neon boundary

DrumToScore uses Neon PostgreSQL and Neon Object Storage. Other Neon primitives stay disabled unless they are deliberately adopted:

- Authentication is the application's own first-party magic-link and session implementation, delivered through Resend.
- Private audio and generated exports use the existing S3-compatible boundary backed by the private `drumscribe-private` bucket.
- Neon requires path-style S3 addressing and does not currently expose `CopyObject`; the adapter streams recoverable moves through a temporary local file.
- `DRUMSCRIBE_S3_SERVER_SIDE_ENCRYPTION=auto` omits unsupported AWS SSE request headers for Neon while retaining provider-managed at-rest encryption.
- API and background work run in separate application and worker containers on Oracle Always Free for the initial beta.
- The runtime database URL must use Neon's pooled connection string. Alembic migrations must use the direct, unpooled connection string.
- Neon's canonical libpq URL is normalized centrally for SQLAlchemy `asyncpg`: TLS remains required while unsupported libpq-only query parameters are removed before connecting.
- The project-scoped Neon MCP configuration is for development and testing, not a production runtime dependency.
- Create database changes on a temporary Neon branch first, run tests there, and apply them to the default production branch only after review.
- An existing public-read Neon bucket named `drumstick` was observed but is intentionally not wired to customer audio. DrumToScore's storage safety gate requires private S3-compatible storage.

## Secret handling

- `.env` is Git-ignored, mode `0600`, and currently contains only local pre-launch values.
- Local managed-service credentials are also stored in macOS Keychain under DrumScribe-specific service names.
- No committed example contains a real DSN, token, password, or connection string.
- Production secrets live in the Oracle host's root-only `/etc/drumscribe/drumscribe.env` and must never be committed or baked into images.
- The ML worker retrieves one immutable private bundle from Neon Object Storage at startup and verifies both the archive SHA-256 and the allowlisted checkpoint hashes before Celery starts. Public model caches are baked from exact pinned revisions and used offline at runtime.

## Launch gates that remain external

1. Wait for Resend to finish its asynchronous DNS verification, then confirm live delivery from `sign-in@drumtoscore.com`.
2. Preserve the owner-attested commercial approval record for the exact pinned Demucs, Beat This, ADTOF, and first-party model artifacts. The fail-closed validator accepts only the recorded approval reference and approved versions; any model or weight change reopens this gate.
3. Complete legal-entity/address decisions and qualified review of the customer-facing legal text.
4. Run a backup restore drill and repeat deletion/security tests on the deployed environment.
5. Complete merchant-of-record onboarding, create the $15 one-time 10-credit product, configure and verify the signed webhook in test mode, then repeat in live mode and enable checkout. Payment stays disabled until the owner explicitly approves this work.
6. Approve a capacity and availability plan before promising an SLA or scaling beyond the single free host.
