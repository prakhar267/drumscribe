# Production services

This is the non-secret source of truth for DrumToScore's pre-launch service topology. Credentials live only in the deployment platform, the ignored local `.env`, or macOS Keychain.

## Service map

| Product boundary | Service | App configuration | Current pre-launch status |
| --- | --- | --- | --- |
| PostgreSQL | Neon project `drumstick` (`cool-cell-64604736`), organization `Prakhar` (`org-winter-sea-89158570`), AWS Ohio | `DRUMSCRIBE_DATABASE_URL` | CLI/MCP are configured. All migrations passed first on an ephemeral branch and then on `production`; pooled application connectivity is verified. |
| Durable queue and rate-limit state | Private Valkey 8 on the Oracle production VM, Mumbai | `DRUMSCRIBE_REDIS_URL=redis://valkey:6379/0`; production uses `DRUMSCRIBE_QUEUE_BACKEND=celery` | Append-only persistence, `noeviction`, health checking and the private `valkey-data` volume are enabled. The service has no host-published port. Localhost stays `inline` so it remains usable without a separate worker process. Upstash is no longer in the production path. |
| Private audio and exports | Neon Object Storage bucket `drumscribe-private`, AWS Ohio | `DRUMSCRIBE_S3_*` | Private bucket, scoped production credential, exact-origin CORS, signed browser upload/download, unsigned denial, streamed move fallback, and cleanup are live-verified. The production API keeps CORS aligned with `https://drumtoscore.com`, `https://www.drumtoscore.com`, and the fallback Workers URL. Neon Object Storage is beta, so application retention/deletion remains authoritative. The existing public-read `drumstick` bucket is unused for customer media. |
| Authentication | Neon Auth (managed Better Auth) on the Neon `production` branch | Web: `NEXT_PUBLIC_AUTH_PROVIDER=neon`, `NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET`; API: `DRUMSCRIBE_NEON_AUTH_BASE_URL`, `DRUMSCRIBE_NEON_AUTH_JWKS_URL` | Email/password, verified email, password reset and social OAuth are implemented. The API exchanges the Neon JWT into the existing first-party product session so project ownership remains unchanged. The legacy magic-link API is retained only as a development fallback and is not the production sign-in path. |
| Transactional authentication email | Resend SMTP through Neon Auth | Neon Auth email-provider configuration; no browser secret | `drumtoscore.com` is verified with DKIM, SPF and DMARC records through Cloudflare. Neon Auth uses `smtp.resend.com` and `sign-in@drumtoscore.com` for account verification and password-reset email; ordinary password sign-in does not send a new link. |
| Inbound customer email | Cloudflare Email Routing | DNS-managed routing only; no application secret | Free routing is enabled for `support@`, `privacy@`, `copyright@`, and `security@drumtoscore.com`; each active rule forwards to the founder's verified Gmail destination. The `support@` route was live-tested with a production DrumToScore email on 10 September 2026. |
| Merchant of record and credits | Dodo Payments | `DRUMSCRIBE_BILLING_*`, `DRUMSCRIBE_DODO_*`, `NEXT_PUBLIC_BILLING_ENABLED` | Free jobs are limited server-side to 30 seconds; complete songs use one credit from the one-time USD 15/10-credit pack. Dodo verification is complete and production checkout is live. |
| API error monitoring | Sentry `python-fastapi` | `DRUMSCRIBE_SENTRY_DSN`, `DRUMSCRIBE_SENTRY_TRACES_SAMPLE_RATE` | SDK wiring and a live ingestion event are verified. |
| Web error monitoring | Sentry `drumscribe-web` | `NEXT_PUBLIC_SENTRY_DSN`, `SENTRY_DSN`, sample-rate variables | Next.js client, server, edge, global-error, and build integration are complete. The least-privilege `SENTRY_AUTH_TOKEN` GitHub Actions secret was installed on 15 September 2026; CI verifies the upload during a trusted build. |
| Public web | Cloudflare Workers, `drumscribe-web` | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_DEMO_MODE`, `API_ORIGIN` | Production mode is live at `https://drumtoscore.com`; `www` redirects to the canonical host with its path and query intact. Cloudflare enforces HTTPS, TLS 1.2+, and the verified response-security headers. Both Workers routes and the same-origin `/api/v1/*` proxy are verified; the Workers URL remains a fallback. |
| Public API, worker, and scheduler | Oracle Cloud Always Free Ampere A1, Mumbai | Root-only environment file, Docker Compose, Caddy TLS | `drumscribe-production` is live on 4 OCPUs/24 GB with a 46.6 GB boot volume, consuming the console-confirmed free A1 allowance. API readiness, Celery worker, Celery Beat, model-bundle verification, Redis TLS, firewalling, and public HTTPS are verified. The fast single-model separator measured 37s versus 134s for the quality ensemble on the same 36.37s input, with a 0.17-point F1 change on the two-track validation. No load balancer, NAT gateway, reserved IP, paid plan, or card action was used. |
| GPU source separation | Modal `drumtoscore-separator`, Asia-Pacific South route | `DRUMSCRIBE_MODAL_DEMUCS_*`; protected proxy token | A scale-to-zero L4 endpoint runs the same hash-pinned `htdemucs` model and returns lossless FLAC to the Oracle worker. A controlled warm 180-second input completed the remote call in 8.38s; cold scale-from-zero tests took 20.70–26.81s. A 45-second parity run matched the local model at 99.71% waveform correlation and 97.36% downstream event F1. The workspace has no payment method and a $1 hard cap; inference stops at the cap rather than charging. Oracle local Demucs remains the rollback path. |
| Logs and uptime | GitHub Actions scheduled probe plus Sentry | `PUBLIC_WEB_URL`, `PUBLIC_API_HEALTH_URL`, and the Sentry variables above | The canonical public web and proxied API readiness endpoint are configured as repository variables and checked every 15 minutes by `.github/workflows/uptime.yml`; failed runs use the repository owner's GitHub Actions notification settings. Better Stack remains optional. |
| Source and CI | Public GitHub repository `prakhar267/drumscribe` | Repository secrets and workflows | Hosted Actions are enabled on the public repository. Secret scanning, push protection, vulnerability alerts, and Dependabot security updates are enabled; the local parity suite remains required before push. |

## Neon boundary

DrumToScore uses Neon PostgreSQL and Neon Object Storage. Other Neon primitives stay disabled unless they are deliberately adopted:

- Authentication uses Neon Auth (managed Better Auth). Neon owns credential and
  identity-provider handling; the web server keeps the Neon Auth cookie secret
  server-side, and the API validates the Neon JWKS before exchanging identity
  into the existing owner-scoped application session.
- Production email/password requires email verification. Neon Auth sends
  verification and password-reset mail through the configured Resend SMTP
  provider. Legacy magic-link routes remain for local/fallback compatibility and
  are not advertised or selected in production.
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
- The Modal deployment credential remains in the local Modal CLI profile. The
  separate endpoint proxy token is stored locally in a mode-`0600` file and in
  the root-only Oracle environment; neither value is committed or returned to
  browsers.
- The ML worker retrieves one immutable private bundle from Neon Object Storage at startup and verifies both the archive SHA-256 and the allowlisted checkpoint hashes before Celery starts. Public model caches are baked from exact pinned revisions and used offline at runtime.

## Launch gates that remain external

1. Privately archive and obtain legal review of the actual rightsholder grants for the exact pinned Demucs, Beat This, ADTOF, and first-party model artifacts. The existing owner attestation and fail-closed validator record an engineering decision; they do not independently prove commercial rights. Any model or weight change reopens this gate.
2. Obtain qualified review of the customer-facing legal, international consumer,
   privacy and current GST wording. The founder-supplied individual operator,
   address and policy decisions are now recorded and published in source.
3. Repeat backup/restore and deletion/security drills before material releases.
   The 15 September no-card rehearsal passed 19 lifecycle/security tests, exact
   17-table Neon branch row-count and schema parity, private-object
   playback/export/delete/byte-exact restore, final canary cleanup and all nine
   public edge checks without reading or changing a customer object. Evidence is
   in `docs/audit/operations-drill-2026-09-15.md`.
4. Monitor the first genuine Dodo purchase for a signed HTTP `200` webhook and
   one exactly-once 10-credit grant. Live checkout-display verification passed
   without a real purchase; no card or charge was used for activation testing.
5. Improve and independently validate full-mixture accuracy before advertising a
   broad percentage. The fresh 12 September isolated-drum control reached 91.34%
   five-family F1, while its constructed full-mix diagnostic reached 61.64%.
6. Approve paid redundant capacity before promising an SLA or scaling beyond the
   single free host. The free-beta thresholds and measured evidence are documented
   in `OPERATIONS.md` and `docs/audit/launch-readiness-2026-09-12.md`.
7. Create a least-privilege Sentry organization token and save it as the GitHub
   Actions secret `SENTRY_AUTH_TOKEN` before expecting CI/deployment builds to
   upload browser source maps. Runtime error ingestion works without it; source
   map upload does not.
