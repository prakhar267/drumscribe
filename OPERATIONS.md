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

The safe beta drill has two parts. First, create a short-lived Neon branch from
`production`, compare exact row-count and normalized schema fingerprints, and
delete the branch. This validates Neon's copy-on-write recovery path without
exporting customer rows. Second, use a schema-only branch with a synthetic
canary, run PostgreSQL 18 `pg_dump`/`pg_restore` into a fresh database, compare
the canary hash, verify the Alembic head, and delete the branch. Never restore a
production dump into a public or shared environment.

Run the read-only edge drill with:

```sh
python3 scripts/audit_production_security.py
```

## Capacity and rollback

Watch processing seconds/audio minute, queue wait, scratch-disk high-water mark,
memory, FFmpeg CPU and provider concurrency. Scale API and workers separately.
Keep a global queue admission limit so provider or GPU saturation cannot become an
unbounded cost event.

### Free-beta capacity policy

- Keep exactly one API, one worker at concurrency `1`, and one scheduler on the
  current 1 OCPU/6 GB Oracle host. Do not promise an SLA on this single host.
- Run the CPU-heavy worker at niceness 10 so an active transcription yields CPU
  time to the API, proxy and scheduler. This improves control-plane responsiveness
  but does not add throughput or redundancy.
- Warn at 70% RAM or disk, 70% CPU for 15 minutes, queue age of 10 minutes, or
  three job failures in 15 minutes. Stop new uploads at 85% RAM or disk, queue
  age of 30 minutes, or readiness failure.
- The host snapshot on 10 September 2026 showed 4.5 GiB available RAM, 22 GiB
  free disk, near-zero idle load, and four healthy/running containers. This is
  an idle baseline, not a transcription throughput measurement.
- The 12 September production-equivalent capacity check processed one 180-second
  rights-cleared track in 34 minutes 16 seconds: 33 minutes 29 seconds in
  HTDemucs-ft and about 47 seconds in recall fusion. Worker CPU remained near
  one full core, peak cgroup memory was 3.70 GiB, and public readiness stayed
  HTTP 200 while observed response time rose to 1.7--2.6 seconds. This is about
  11.4x slower than real time and is a failed throughput target, not a launch
  SLA. Six- and twelve-minute repetitions were not run because linear runtime
  would exceed the one-hour job limit and provide no new capacity evidence.
- The same audit removed 21.08 GB of unused, regenerable Docker build cache;
  active images, volumes and both current and rollback release tags were kept.
  Root-disk use fell from 78% to 40%.
- GitHub's scheduled probe is a best-effort free alert and can run later than
  its 15-minute cron expression. Do not call it a 15-minute detection SLA. Add
  a redundant monitor only after choosing a provider that needs no card.

Application rollback may use only a schema-compatible release. Do not downgrade
the database destructively. Disable a bad provider/model through reviewed
configuration, preserve stored provenance, drain affected jobs, and replay only
from the last durable successful stage.
