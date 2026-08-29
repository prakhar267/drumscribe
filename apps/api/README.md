# DrumScribe API

FastAPI owns DrumScribe's private project data, authenticated sessions, direct uploads,
processing orchestration, canonical events, revisions, and exports. PostgreSQL is the
production source of truth; Redis/Celery dispatches durable work; customer media is kept in a
private S3-compatible bucket and exposed only through short-lived signed URLs.

## Local development

Python 3.12+ and `uv` are required. From this directory:

```bash
cp .env.example .env
uv sync --dev
uv run alembic upgrade head
uv run uvicorn drumscribe_api.main:app --reload
```

For a dependency-free local media loop, set `DRUMSCRIBE_STORAGE_BACKEND=local`,
`DRUMSCRIBE_LOCAL_STORAGE_PATH=.local-storage`, and `DRUMSCRIBE_QUEUE_BACKEND=inline`.
The inline queue is only a development convenience; production startup rejects it. Local signed
upload/download routes enforce the same HMAC expiry and authorization model as S3 URLs.
When S3/MinIO has a private container hostname, set `DRUMSCRIBE_S3_ENDPOINT_URL` to that internal
address and `DRUMSCRIBE_S3_PUBLIC_ENDPOINT_URL` to the browser-reachable address. Object operations
remain on the private endpoint while upload/download signatures contain the public host.
Set `DRUMSCRIBE_S3_CONFIGURE_BUCKET_CORS=true` only for a deployment identity allowed to manage
the bucket. Startup then installs an exact-origin browser CORS policy from
`DRUMSCRIBE_WEB_ORIGINS`: `GET`/`HEAD`/`PUT`, the signed `Content-Type` and server-side-encryption
headers, and exposed `ETag`. Production rejects wildcard web origins. If infrastructure manages
the bucket instead, apply the equivalent rule before serving browser traffic.

Request `POST /api/v1/auth/anonymous-session` first. It sets an opaque HttpOnly session cookie.
Swagger is available at `/docs` outside production. Magic-link request responses never reveal
whether an account exists. A development-only token is returned only when
`DRUMSCRIBE_DEV_EXPOSE_MAGIC_LINK=true`; production validation forbids that setting.

Operational probes are intentionally separate: `GET /api/v1/health/live` proves only that the
API process can serve requests, while `GET /api/v1/health/ready` concurrently checks the database,
queue broker, private storage bucket, and production-provider configuration. Readiness is bounded
by `DRUMSCRIBE_READINESS_TIMEOUT_SECONDS` per dependency and returns HTTP 503 with per-dependency
status when any required service is unavailable. The legacy `GET /api/v1/health` endpoint remains
available for compatibility. Production rate limits use a Redis-backed atomic sliding window
shared across API replicas; only development/testing use the in-memory implementation. If Redis is
unavailable, authentication routes fail closed with HTTP 503 while general traffic fails open and
emits a structured operational error.

Run all checks:

```bash
uv run ruff check src tests
uv run mypy --no-incremental src
uv run pytest
uv run alembic upgrade head
```

The worker imports `drumscribe_api.tasks`. The deterministic development pipeline remains useful
without external ML credentials, while production is expected to install and configure the
commercially approved `drumscribe_music` provider package.

## Security invariants

- Ownership-scoped queries return 404, preventing identifier enumeration.
- Upload filenames never enter storage keys or shell commands.
- MIME declarations are checked at presign time and actual bytes are probed before processing.
- Upload completion checks only private-object metadata and size; the durable `VALIDATING` worker
  stage materializes and probes codecs/duration so a 150 MB object never blocks an HTTP request.
- Customer objects are private and signed for minutes, not published.
- Project deletion moves recoverable objects to new private quarantine keys before returning, so
  already-issued download URLs are revoked immediately; retention permanently deletes the
  quarantined objects after the configured restore window.
- Session and magic-link secrets are only stored as SHA-256 hashes.
- The right-to-upload acknowledgement is mandatory and audited.
