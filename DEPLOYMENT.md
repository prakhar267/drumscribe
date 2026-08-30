# Deployment

## Supported topology

Deploy the web, API, and worker as separate containers. Use managed PostgreSQL, a durable Redis/Valkey service, and private S3-compatible object storage. Put the web and API behind one TLS-terminating edge so secure session cookies remain first-party. Workers require FFmpeg/FFprobe and should run with no inbound network exposure.

The provided Compose stack is for local development and acceptance testing. The mutable MinIO image tags are intentionally limited to local use; production must pin reviewed image digests.

## Release checklist

1. Generate a unique 32+ byte application secret and store it in the platform secret manager.
2. Use Neon's pooled PostgreSQL URL for the API and worker. Run `alembic upgrade head` once as a release job with Neon's direct, unpooled URL.
3. Create a private bucket with block-public-access and narrowly scoped workload credentials. `DRUMSCRIBE_S3_SERVER_SIDE_ENCRYPTION=auto` omits unsupported AWS SSE request headers for Neon Object Storage and Cloudflare R2 while retaining `AES256` for AWS/MinIO. When the provider does not expose lifecycle or versioning controls, the retention worker and recoverable delete prefixes are authoritative.
4. Set `DRUMSCRIBE_S3_PUBLIC_ENDPOINT_URL` to a browser-reachable TLS endpoint while keeping `DRUMSCRIBE_S3_ENDPOINT_URL` private.
5. Provision exact-origin bucket CORS for `GET`, `HEAD`, and signed `PUT` plus the required `Content-Type` headers. Set `DRUMSCRIBE_S3_CONFIGURE_BUCKET_CORS=true` only when the API workload is intentionally allowed to manage that policy; otherwise manage the equivalent rule in infrastructure.
6. Set secure cookies, exact API CORS origins, trusted proxy ranges, and Redis-backed production rate limits. Set `DRUMSCRIBE_ALLOWED_HOSTS` to the public API hostname and retain a one-year-or-longer `DRUMSCRIBE_HSTS_MAX_AGE_SECONDS` after TLS is verified.
   Managed dependencies can cold-start; keep `DRUMSCRIBE_READINESS_TIMEOUT_SECONDS=10` unless target-region measurements justify a lower bounded value.
7. Configure Resend or the magic-link delivery webhook and its secret; disable development token exposure. Resend requires a verified sending domain before emails can be sent to customers.
8. Set `DRUMSCRIBE_PIPELINE_PROVIDER=music_engine` and select only provider adapters whose exact code, weights, data, contract, and commercial use are approved in `MODEL_LICENSING.md`. The repository intentionally ships no pre-approved commercial model.
9. Run Celery workers and exactly one Celery Beat (or equivalent managed scheduler) so retention and deletion purges execute. Compose uses `worker --beat` only for a single-node local stack.
10. Configure Sentry-compatible exception/tracing capture with filename and audio-metadata redaction.
11. Run web, API, music-engine, migration, authorization, signed-URL, bucket-CORS, and full-stack browser tests against the release images.
12. Verify backup restore, anonymous retention, quarantine restore/purge, project deletion, and account deletion in the target environment.

The concrete free-service mapping and its verified pre-launch status are tracked in [`docs/PRODUCTION_SERVICES.md`](docs/PRODUCTION_SERVICES.md). Do not copy DSNs, passwords, API keys, or database URLs into that file or any committed configuration.

## Scaling

Scale API processes independently from workers. Queue routing can later separate CPU normalization, GPU separation/transcription, and export work without changing the REST contract. Keep stage outputs deterministic and checkpointed so a retry starts at the last successful stage. Use per-user and global concurrency controls before increasing worker count.

## Rollback

Application rollback must not downgrade the database destructively. Mark migrations with their compatibility window, deploy additive schema changes before consumers, and perform removals only after the old release is no longer runnable. Model versions and provider parameters are stored per run, so inference regressions can be rolled back independently.
