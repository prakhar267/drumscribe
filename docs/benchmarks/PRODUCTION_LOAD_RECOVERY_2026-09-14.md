# Production load, recovery, and timing verification — 14 September 2026

## Scope

This launch check exercised the public `https://drumtoscore.com` API as a user,
not an in-process test double. It covered simultaneous submissions, worker
process failure, durable recovery, cleanup, and a fresh three-minute timing run.
All audio was rights-cleared test material. No payment card or paid cloud action
was used.

## Infrastructure correction found during preflight

The old Upstash Redis free quota had reached its 500,000-request limit and the
worker was crash-looping. Production now uses private persistent Valkey on the
Oracle VM for Celery and rate limiting:

- Valkey 8 with append-only persistence and `noeviction`;
- no host-published Redis port;
- container health check and persistent `valkey-data` volume;
- queue readiness measured between roughly 0.6 ms and 2.8 ms during rollout.

This removes a request-capped third-party queue from the production critical
path. The change shipped in commit `562cdaa`.

## Three simultaneous users

Three anonymous users uploaded the same 45-second, 7,938,118-byte WAV and
submitted nearly simultaneously. The submissions were observed at 0.0002,
0.0004, and 0.0005 seconds from the release point.

| Job | READY from submission | Drum events | Beats | Tempo | Retries |
| --- | ---: | ---: | ---: | ---: | ---: |
| `42c8c137-7ffd-46b2-a178-3a6ef517311a` | 120.252 s | 318 | 82 | 107.143 BPM | 0 |
| `e7ebc11b-3d42-45e5-9c75-db42cda0a9d5` | 205.757 s | 318 | 82 | 107.143 BPM | 0 |
| `c5a2e75a-5c68-4748-8cbc-130884fe4b31` | 290.870 s | 318 | 82 | 107.143 BPM | 0 |

All three jobs completed successfully and returned identical event/beat counts.
Production intentionally runs one CPU transcription worker, so jobs were
serialized rather than lost. This is safe beta behavior, but queue delay grows
approximately linearly under bursts until more worker capacity is added.

## Worker failure and recovery

The first administrative `docker kill` check demonstrated a Docker behavior:
an explicit administrator stop suppresses the `unless-stopped` restart policy.
The worker was restarted manually and the durable job checkpoint resumed.

Production was then hardened with a startup reconciler. Before the single worker
accepts tasks, it requeues database-backed non-terminal jobs that had progressed
beyond `RECEIVED`. Duplicate/stale Redis delivery is safe because the pipeline
returns immediately for missing or terminal jobs.

A second test killed the worker's host process to simulate an actual crash:

- crash: `2026-09-14T08:12:59Z`;
- Docker restart: under one second, with container start at
  `2026-09-14T08:12:59.707952778Z`;
- worker startup log: `requeued_interrupted_jobs=1`;
- interrupted job `1bc6518d-e975-4671-b11b-5213c32e9a67` reached READY in
  120.371 seconds with 312 events, 82 beats, and zero retries;
- worker container remained running with `restartCount=1` after the test.

The recovery and materialization optimization shipped in commit `f0c7b4a`.

## Three-minute production timing

The post-change registered-user test used a 180.000-second MP3 made losslessly
in duration from the same rights-cleared source fixture. Its SHA-256 was
`f1a0da9f805987e4b25732c9cf1f6644a277ef3b09b14f0b65fb469c51deacf2`.

| Measurement | Earlier production run | Post-change run | Improvement |
| --- | ---: | ---: | ---: |
| Submission to READY | 153.802 s | 141.517 s | 12.285 s (8.0%) |
| Output events | 1,258 | 1,276 | informational, not an accuracy score |
| Beat count | 325 | 325 | unchanged |
| Retries | 0 | 0 | unchanged |

The optimization reuses the already materialized full-mixture file when the
primary and recall-fusion inputs have the same storage key. This eliminates a
duplicate object-storage download without changing model thresholds or the
notation algorithm.

The reusable probe initially exposed a helper-only fault: its registered mode
forwarded the DrumToScore bearer token to the Neon presigned upload URL. Neon
correctly returned `403 AccessDenied`. The helper now uses a separate HTTP
request for object storage, preventing credential leakage and preserving the
S3 signature. The production upload API itself was not the cause. A repeat
registered upload and full run succeeded after the fix.

## Final state and limits

- Public API health and readiness returned HTTP 200.
- No non-terminal jobs remained after testing.
- No active `production-probe-*` accounts remained.
- Main Celery queue length was zero.
- One deliberately stale unacknowledged delivery from the crash test remains
  under Redis visibility timeout; its associated test job/account has already
  been deleted, so delivery will be acknowledged as a no-op.
- The single Oracle worker provides recovery, not parallel throughput. For a
  marketing burst, scale worker capacity only after paid Modal capacity is
  explicitly enabled and another sealed concurrency run passes.
- Modal performs GPU source separation; Oracle hosts the API, queue, CPU
  transcription, beat detection, and notation. Removing Modal configuration
  restores Oracle CPU separation manually. Modal outage fallback is not
  automatic.
- The free-plan copy remains unchanged by request: anonymous preview is 90
  seconds and the first registered full-song transcription is free.
