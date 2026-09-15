# Operations, deletion and recovery drill — 15 September 2026

This release rehearsal used no payment card, paid plan, customer audio, private
object name or secret. No production customer row or object was changed or
deleted. The only cloud deletion removed the exact disposable Neon branch
created by this drill.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Local deletion, restore and upload-security suite | Pass | `19 passed` in 3.32 seconds across `test_retention_lifecycle.py` and `test_upload_security.py` |
| Production private-object canary | Pass | Unique `operations-canary/2026-09-15/` keys; signed WAV playback, MusicXML parse, delete, byte-exact restore and final cleanup passed; `customerObjectsAccessed=0` |
| Neon branch recovery rehearsal | Pass | Read-only `ops-restore-drill-20260915` cloned from `production`; all 17 public-table counts, normalized schema and Alembic head matched; exact branch deleted |
| Public edge/security audit | Pass | 9/9 checks passed: HTTPS, headers, HSTS, HTTP and canonical redirects, readiness, unauthorized denial, hostile CORS denial and certificate |
| Sentry source-map credential audit | Blocked externally | Web build config reads `SENTRY_AUTH_TOKEN`; GitHub repository had zero Actions secrets and no local upload token was present. Runtime DSNs exist, but they cannot authorize source-map upload |

The object canary restored audio SHA-256 was
`56d4af65701c26df20bd4021eda95b6e830348ce3a746086079fe89285548dc9`.
The normalized production/clone schema SHA-256 was
`87a21159497afbe6ec7dc1f40efb94ee373cee3d70b3437fa2f35ff776a16a40`,
the non-secret row-count fingerprint was
`5cf0a05187ccd2fd61c5c14df2aba2e6099e182d986854720a3c53118a634768`,
and both branches reported Alembic revision `9f4b8d16a2c7`.

The raw table counts were compared in temporary local files and were not added to
Git. PostgreSQL schema dumps contained no row data. PostgreSQL 18 adds a random
`\\restrict` token to each dump; those two non-schema lines were removed before
the byte-for-byte schema comparison.

## Commands

```sh
cd apps/api
uv run pytest tests/test_retention_lifecycle.py tests/test_upload_security.py

cd ../..
PYTHONPATH=apps/api/src uv run --project apps/api \
  python scripts/storage_restore_canary.py \
  --prefix operations-canary/2026-09-15

python3 scripts/audit_production_security.py
```

The Neon rehearsal used the authenticated CLI to create a read-only branch with
a 24-hour expiry, compare count/schema/revision fingerprints, and immediately
delete that named branch. Connection strings were kept in process variables and
were never printed or written to this record.

## Remaining external action

Create a least-privilege Sentry organization token allowed to create releases
and upload source maps for `prakharorg/drumscribe-web`, then store it as the
GitHub Actions secret `SENTRY_AUTH_TOKEN`. The current operator must do this in
the Sentry account; no token can be derived from the runtime DSN. Rotate it under
the normal secret policy and never expose it to the browser.
