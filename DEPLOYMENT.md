# Deployment

## Supported topology

Deploy the web, API, and worker as separate containers. Use managed PostgreSQL, a durable Redis/Valkey service, and private S3-compatible object storage. Put the web and API behind one TLS-terminating edge so secure session cookies remain first-party. Workers require FFmpeg/FFprobe and should run with no inbound network exposure.

The provided Compose stack is for local development and acceptance testing. The mutable MinIO image tags are intentionally limited to local use; production must pin reviewed image digests.

## Release checklist

1. Generate a unique 32+ byte application secret and store it in the platform secret manager.
2. Use a dedicated database role and run `alembic upgrade head` once as a release job.
3. Create a private bucket with block-public-access, encryption, versioning/lifecycle rules, and narrowly scoped workload credentials.
4. Set `S3_PUBLIC_ENDPOINT_URL` to a browser-reachable TLS endpoint while keeping the internal endpoint private.
5. Set secure cookies, exact CORS origins, trusted proxy ranges, and production rate limits.
6. Configure SMTP and Google OAuth callback URLs if those sign-in methods are enabled.
7. Set `ALLOW_RESEARCH_PROVIDERS=false`; production startup must reject unresolved or non-commercial providers.
8. Configure Sentry-compatible exception capture and an OTLP endpoint, with filename/audio metadata redaction enabled.
9. Run web, API, music-engine, migration, authorization, and signed-URL tests against the release image.
10. Verify backup restore, anonymous retention, project deletion, and account deletion in the target environment.

## Scaling

Scale API processes independently from workers. Queue routing can later separate CPU normalization, GPU separation/transcription, and export work without changing the REST contract. Keep stage outputs deterministic and checkpointed so a retry starts at the last successful stage. Use per-user and global concurrency controls before increasing worker count.

## Rollback

Application rollback must not downgrade the database destructively. Mark migrations with their compatibility window, deploy additive schema changes before consumers, and perform removals only after the old release is no longer runnable. Model versions and provider parameters are stored per run, so inference regressions can be rolled back independently.

