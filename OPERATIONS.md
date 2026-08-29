# Operations

## Service topology

Run the Next.js web service, FastAPI service, Celery workers and exactly one
Celery Beat scheduler as independently deployable processes. PostgreSQL, Valkey
and private object storage are durable dependencies. Workers need FFmpeg,
FFprobe, temporary disk and outbound access only to storage plus approved ML
providers; they need no inbound public port.

## Health and alerts

- Liveness: `GET /api/v1/health` proves the API process can answer.
- Readiness: `GET /api/v1/health/ready` checks database, queue, storage and the
  selected pipeline configuration. Remove an instance from traffic on failure.
- Alert on readiness failure, elevated 5xx/429 rates, queue age, failed/retried
  jobs, provider timeouts, retention failures, storage errors and magic-link
  delivery failures.
- Track provider success, p50/p95 duration, cost/audio minute, request IDs and
  retention expiry without logging media URLs or names.

## Routine runbooks

1. Before release, run `make ci`, migration upgrade/check and the full Compose
   acceptance workflow.
2. Apply additive migrations as a one-shot release job before new consumers.
3. Verify one worker and one scheduler heartbeat before accepting uploads.
4. Review failed jobs by ID in restricted admin diagnostics. Use provider request
   IDs for escalation; never paste signed URLs into tickets.
5. Retention runs hourly. Alert if no successful run occurs for two hours.
6. Rotate session, database, object-storage, mail and provider secrets through the
   deployment secret manager. A session-secret rotation logs out all users.

## Backup and restore

Enable managed PostgreSQL PITR and encrypted daily snapshots. Object storage must
use encryption, versioning only when compatible with deletion obligations, and
lifecycle rules aligned with `DATA_RETENTION.md`. Quarterly, restore the database
to an isolated environment, restore a sampled private object, verify ownership,
run migrations, open/export a project, then destroy the drill environment.

## Capacity and rollback

Watch processing seconds/audio minute, queue wait, scratch-disk high-water mark,
memory, FFmpeg CPU and provider concurrency. Scale API and workers separately.
Keep a global queue admission limit so provider or GPU saturation cannot become an
unbounded cost event.

Application rollback may use only a schema-compatible release. Do not downgrade
the database destructively. Disable a bad provider/model through reviewed
configuration, preserve stored provenance, drain affected jobs, and replay only
from the last durable successful stage.
