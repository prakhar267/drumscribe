# Production operations audit — 10 September 2026

## Safety boundary

- No card, checkout, paid plan, or paid infrastructure feature was used.
- No production customer row or object was changed or deleted.
- The only destructive cloud operations deleted two disposable Neon branches
  created for this drill. Both had 24-hour expiry as a cleanup fallback and are
  now confirmed absent; only `production` remains.
- Temporary database archives contained a schema-only copy plus a synthetic
  canary. They were mode-restricted and deleted after verification.

## Backup and restore evidence

### Neon snapshot parity

A disposable branch was created from `production`. Exact row counts across all
16 public tables and normalized schema output matched the source at the recovery
point. No row contents were exported.

- Row-count fingerprint:
  `05e8687763ed672cdccf67f3ad0447b0f8967bb76a9d75e5ac904cc900466a7d`
- Schema fingerprint:
  `766d83343b78a121656c2944ea64f00f7a4b0b79c411a6b02f186819ab5f9013`
- Result: pass

### PostgreSQL dump/restore mechanics

A separate schema-only Neon branch received one synthetic canary row. A
PostgreSQL 18 custom archive was restored into a new database on that branch.

- Archive SHA-256:
  `1e2f43241e11aba54a03d2a4926508b7f39bd1e80efccedebadba909774c2f67`
- Archive size: 48,601 bytes; archive entries: 112
- Restored public tables: 16
- Restored Alembic revision: `9f4b8d16a2c7 (head)`
- Synthetic canary hash: pass
- Result: pass

This validates snapshot parity and restore mechanics. It does not substitute for
a future authorized full-data restoration and private-object playback/export
drill in a locked staging environment.

## Deletion and retention evidence

The API test suite now explicitly verifies that account deletion revokes the
existing bearer session, hides the project, removes the email identity, marks
the user/project deleted, physically deletes private audio, invalidates the old
signed URL, and leaves every asset in `DELETED` state. Existing tests also cover
recoverable project deletion, expiry purge, abandoned/rejected uploads, export
URL revocation/reissue, replacement uploads, and retention retries.

- Targeted security/retention suite: 38 tests passed
- Production account deleted during the drill: none

## Live read-only security result

All nine automated checks passed after Cloudflare HSTS was enabled:

- HTTPS web response: pass
- HTTP to HTTPS redirect: pass
- `www` canonical redirect with path/query preservation: pass
- required clickjacking/MIME/referrer headers: pass
- hostile-origin CORS preflight denied: pass
- unauthenticated projects request denied: pass
- database/queue/storage/provider readiness: pass
- TLS 1.2 negotiation and certificate validity: pass (89 days remaining)
- homepage HSTS: pass — `max-age=31536000; includeSubDomains`

Cloudflare HSTS is configured for 12 months with subdomains included, preload
off, and no-sniff on. The read-only audit was rerun successfully:

```sh
python3 scripts/audit_production_security.py
```

## Oracle free-host snapshot

- Host uptime: 2 days 1 hour
- Load average: `0.00 0.00 0.00`
- Memory: 5,903 MiB total; 4,498 MiB available
- Root disk: 45 GiB total; 22 GiB free; 51% used
- Containers: API healthy; worker, scheduler, and Caddy running
- Runtime secret file: `root:root`, mode `0600`
- Firewall: default-deny incoming; 80/443 public; SSH limited to owner IP
- Defense in depth completed 12 September: after confirming no NFS mounts,
  `/etc/fstab` entries or reverse dependencies, `rpcbind.socket` and
  `rpcbind.service` were disabled and stopped. Port 111 is closed.

These are idle measurements, not proof of transcription throughput.

## Uptime and capacity

The GitHub uptime workflow passed at
`https://github.com/prakhar267/drumscribe/actions/runs/34407164085` and checks the
canonical website plus API readiness. GitHub scheduled workflows are
best-effort; observed runs were not consistently 15 minutes apart, so this is
not a 15-minute detection SLA.

The approved free-beta policy is one API, one worker with concurrency `1`, one
scheduler, queue backpressure, warning at 70% memory/disk or 10-minute queue age,
and upload admission closure at 85% memory/disk, 30-minute queue age, or failed
readiness. Do not advertise an SLA until a redundant paid plan is explicitly
approved by the owner.

## 12 September follow-up

A synthetic, operations-only private-object canary passed storage health, signed
playback, signed MusicXML export and parsing, deletion, byte-exact restore and
final cleanup. It touched no customer objects. The restored audio SHA-256 was
`56d4af65701c26df20bd4021eda95b6e830348ce3a746086079fe89285548dc9`.

Remaining operations blockers:

1. Confirm GitHub failure notifications reach a monitored human; the free
   scheduler alone is not an on-call system.
2. Finish representative throughput measurement before publishing a processing-
   time promise; the single free CPU worker provides no SLA.
3. Rehearse the support and incident procedure periodically and after material
   provider or data-flow changes.
