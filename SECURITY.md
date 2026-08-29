# Security and privacy

## Trust boundaries

Uploaded media is hostile input. API processes only authorize and enqueue work; isolated worker containers inspect and decode it. User-facing filenames are display metadata and are never interpolated into commands or object keys. Object keys use opaque project/asset IDs and private prefixes.

Every project, asset, event, revision, and export operation is scoped to the authenticated or anonymous session owner. Admin diagnostics require an explicit admin role. Downloads and uploads use short-lived signed URLs; the bucket has no public-read policy.

## Controls implemented by design

- MIME declarations are advisory. FFprobe verifies the container, codec, duration, channel count, and sample rate before processing.
- Configurable byte, duration, rate, and concurrency limits apply before expensive work.
- FFmpeg/FFprobe run through argument arrays with timeouts and constrained working directories.
- Session cookies are HTTP-only, same-site, and secure outside local development. Magic-link tokens are single-use, short-lived, and stored as hashes.
- Production rejects unlisted Host headers and emits one-year HSTS after TLS termination is verified.
- Bulk edits are transactional, authorized, bounded, and revisioned.
- Structured errors contain stable codes; logs exclude raw audio, signed URLs, tokens, and full user filenames.
- Delete operations revoke access immediately and enqueue idempotent asset purging. Account deletion cascades through owned projects.
- `allowModelImprovement` defaults to false and never changes implicitly.

## Production hardening

Run workers as an unprivileged user with a read-only root filesystem, bounded scratch volume, CPU/memory/PID limits, no Docker socket, and outbound network access limited to required object storage and approved model endpoints. Scan images and dependencies, rotate secrets, encrypt data at rest, and enable database point-in-time recovery.

Set an exact origin allow-list; do not use wildcard CORS with credentials. At the edge, add request-body limits, bot/abuse controls, TLS/HSTS, and queue admission limits. Retain audit events longer than transient processing logs but never include media contents.

## Reporting

This private pre-release repository has no public security intake address yet. Establish one before launch and add coordinated-disclosure terms. Legal, privacy, terms, and copyright copy requires counsel review.
