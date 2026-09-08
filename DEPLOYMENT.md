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
8. Set `DRUMSCRIBE_PIPELINE_PROVIDER=music_engine` and select only provider adapters whose exact code, weights, data, contract, and commercial use are approved in `MODEL_LICENSING.md`. The owner-approved self-hosted path must use the exact pinned revisions and hashes recorded in the approval evidence; changing a model or weight requires a new review.
9. Run Celery workers and exactly one Celery Beat (or equivalent managed scheduler) so retention and deletion purges execute. Compose uses `worker --beat` only for a single-node local stack.
10. Configure Sentry-compatible exception/tracing capture with filename and audio-metadata redaction.
11. Run web, API, music-engine, migration, authorization, signed-URL, bucket-CORS, and full-stack browser tests against the release images.
12. Verify backup restore, anonymous retention, quarantine restore/purge, project deletion, and account deletion in the target environment.

The concrete free-service mapping and its verified pre-launch status are tracked in [`docs/PRODUCTION_SERVICES.md`](docs/PRODUCTION_SERVICES.md). Do not copy DSNs, passwords, API keys, or database URLs into that file or any committed configuration.

## Oracle Always Free launch layout

The public `prakhar267/drumscribe` repository deploys from `main` to the Ampere A1 host. Runtime secrets are stored only in `/etc/drumscribe/drumscribe.env` as `root:root` with mode `0600`; they are not baked into images or committed. Caddy is the only public container, and the worker has no inbound port.

| Workload | Image | Exposure | Start command / override | Health and cardinality |
| --- | --- | --- | --- | --- |
| `drumscribe-api` | `infra/docker/api.Dockerfile` | Private Compose network, port `8000` | Migrate, then start Uvicorn | Readiness: `/api/v1/health/ready`; liveness: `/api/v1/health/live`; Caddy proxies the public TLS hostname. |
| `drumscribe-worker` | `infra/docker/worker.Dockerfile` | No public port | Image default, Celery concurrency `1` | Start with one replica. Each replica processes one memory-heavy transcription at a time. |
| `drumscribe-beat` | API image | No public port | Celery Beat with a writable local schedule | Exactly one instance schedules the hourly idempotent retention task. |
| `caddy` | `caddy:2.10.2-alpine` | Public ports `80` and `443` | `infra/oracle/Caddyfile` | Automatic TLS and security headers; persistent certificate state. |

The API and worker use Neon's pooled URL; the API entrypoint applies compatible Alembic migrations before serving traffic. Schema changes are first verified on a temporary Neon branch with its direct URL. All workloads share the production environment, Redis, private-storage, provider-approval, and Sentry configuration, but the API image does not receive the private model-bundle variables. The worker additionally receives:

```text
DRUMSCRIBE_MODEL_BUNDLE_KEY=runtime-models/drumscribe-recall-fusion-v6-f2b01777aae9be87.tar.gz
DRUMSCRIBE_MODEL_BUNDLE_SHA256=f2b01777aae9be874af24dcef06345e13cf15fe516280e1ce07381b7e837d675
```

Its entrypoint downloads that private Neon object, verifies the archive and every approved checkpoint hash, installs it atomically, and only then starts Celery. Public Beat This and Demucs artifacts are revision- and hash-pinned in the image and run with the Hugging Face client offline at runtime. Redis uses `rediss://` with `ssl_cert_reqs=required`.

Until a custom domain exists, the API is `https://api.137.23.63.132.nip.io` and the public web origin is `https://drumscribe-web.prakhargupta267.workers.dev`. The Cloudflare build uses `NEXT_PUBLIC_API_URL=/api/v1`, `NEXT_PUBLIC_DEMO_MODE=false`, and that API hostname as `API_ORIGIN`, so the browser sees a same-origin API and the secure session cookie works reliably.

## Scaling

Scale API processes independently from workers. Queue routing can later separate CPU normalization, GPU separation/transcription, and export work without changing the REST contract. Keep stage outputs deterministic and checkpointed so a retry starts at the last successful stage. Use per-user and global concurrency controls before increasing worker count.

The free launch host is one Oracle `VM.Standard.A1.Flex` instance with 1 OCPU, 6 GB RAM, and a 46.6 GB boot volume. Keep worker concurrency at one and use queue backpressure. This is appropriate for validation and a low-traffic beta, not an advertised availability or processing-time SLA.

- API: one process on the free host. For sustained traffic, move the API to redundant hosts only after the owner explicitly approves a paid capacity plan. The API is stateless, and rate-limit/session state is in Redis.
- Worker: concurrency remains `1`; scale from queue age/depth only after capacity and budget are explicitly approved. Do not increase Celery concurrency inside the free host because Demucs and transcription models are memory-heavy.
- Scheduler: exactly `1` hourly retention job. Never autoscale or duplicate it.
- Neon: retain the current pooled application endpoint and `0.25–2 CU` autoscaling range for beta, then raise the ceiling only after connection, CPU, and latency measurements justify it. Migrations always use the direct endpoint.
- Backpressure: keep the product's per-user concurrent-job limits enabled, watch oldest queued-job age and failure rate, and reject excess work cleanly rather than exhausting workers.
- Model rollout: publish a new immutable private bundle key, deploy a canary worker against it, and then replace workers gradually. Never overwrite a bundle already referenced by a release.

## Rollback

Application rollback must not downgrade the database destructively. Mark migrations with their compatibility window, deploy additive schema changes before consumers, and perform removals only after the old release is no longer runnable. Model versions and provider parameters are stored per run, so inference regressions can be rolled back independently.
