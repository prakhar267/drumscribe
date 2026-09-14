# Oracle Always Free deployment

This deployment runs the public API, one CPU-only transcription worker, one
Celery Beat scheduler, and a Caddy TLS edge on a single Ampere A1 VM. PostgreSQL,
private object storage, email delivery, and error reporting remain managed
services and are configured through `/etc/drumscribe/drumscribe.env`. The
Celery broker and rate-limit store run as a private, persistent Valkey service
on the same VM so production is not coupled to a request-capped free Redis
plan. Set `DRUMSCRIBE_REDIS_URL=redis://valkey:6379/0`; Valkey has no published
host port and persists its append-only log in the `valkey-data` volume.

Production source separation can be delegated to the protected, scale-to-zero
Modal L4 endpoint documented in `infra/modal/README.md`. Oracle keeps the API,
queue worker, transcription, beat tracking and score generation; only the
Demucs separation stage leaves the host. Removing the three
`DRUMSCRIBE_MODAL_*` credential values and restarting the worker restores the
local CPU separator without a code rollback.

`configure_modal_env.py` accepts the endpoint proxy credential and exact Git
release tag as JSON on standard input, validates them, creates a mode-`0600`
timestamped backup and atomically updates the root-only environment. It reports
only the backup path, never the secret values.

The Oracle console currently shows an Always Free Ampere allowance of 3,000 OCPU
hours and 18,000 GB hours monthly, equivalent to 4 OCPUs and 24 GB RAM across the
tenancy. Keep the sum of every running A1 instance inside that allowance. The
DrumToScore production VM uses the full 4 OCPUs and 24 GB RAM, plus a 46.6 GB
boot volume inside the 200 GB Always Free block-volume allowance. Stop or
downsize production before creating another A1 instance, even for recovery.

Run the stack from the repository root:

```sh
sudo docker compose \
  --env-file /etc/drumscribe/drumscribe.env \
  --file infra/oracle/compose.yaml \
  up --detach --build
```

The environment file must be owned by root with mode `0600`. It must define an
exact public hostname in `DRUMSCRIBE_API_HOST`, production-safe application
settings, and the hash-pinned private model bundle variables. Never commit that
file or copy secret values into logs.

After enabling Neon Auth on the production branch, apply its public endpoint and
the release revision atomically. The helper validates the production Neon host,
keeps a mode-`0600` backup, and never reads or prints other environment values:

```sh
sudo python3 infra/oracle/configure_neon_auth_env.py \
  /etc/drumscribe/drumscribe.env \
  https://ep-example.neonauth.us-east-2.aws.neon.tech/neondb/auth \
  <git-revision>
```

Only TCP 80/443 are publicly exposed by the stack. The API and worker stay on the
private Compose network, and the worker has no inbound port. Restrict SSH at both
the OCI network layer and the host firewall.

The worker starts through `nice -n 10` so model inference yields CPU time to the
public API and scheduler on the four-OCPU beta host. Keep Celery concurrency at
one until a sealed capacity run proves that greater concurrency preserves API
readiness; niceness protects responsiveness but does not make the free host
suitable for an advertised processing-time or availability SLA.

Immediately before the single worker starts, `drumscribe_api.worker_recovery`
requeues every non-terminal job that had advanced beyond `RECEIVED`. This
closes Redis visibility-timeout downtime after a worker or VM process crash.
The durable stage checkpoint reruns the interrupted stage; if the broker's old
delivery becomes visible later, the terminal-state guard turns it into a no-op.
This startup reconciler assumes this Compose deployment's single-worker model;
replace it with leased job ownership before horizontally scaling workers.

The original 13 September 2026 180-second production-equivalent probe took 10
minutes 26 seconds on 4 OCPUs/24 GB with the four-model HTDemucs-ft ensemble.
A same-input separator A/B later measured 134 seconds for HTDemucs-ft and 37
seconds for the single HTDemucs model on a 36.37-second rights-cleared mixture.
On the two-track, 105-second notation check, HTDemucs changed five-family F1 at
50 ms from 61.64% to 61.47% while the two full separation/transcription runs
completed in 55 and 70 seconds. Production selects the pinned model with
`DRUMSCRIBE_DEMUCS_MODEL`; the launch setting is `htdemucs`, while
`htdemucs_ft` remains the rollback quality ensemble. See
`docs/benchmarks/ORACLE_FAST_SEPARATOR_2026-09-13.md` for the measured boundary.
Before any later resize, inspect all tenancy A1 allocations and confirm the new
total remains inside the documented Always Free allowance; never select a paid
shape or attach a payment method without explicit approval.

## Dodo live activation

After Dodo confirms merchant verification, first verify the staged live product
and webhook through Dodo's live API. Then promote the already staged credentials
without printing them:

```sh
sudo python3 infra/oracle/activate_dodo_live_env.py \
  /etc/drumscribe/drumscribe.env
```

The utility requires the exact DrumToScore return/cancel URLs, a `pdt_` live
product ID, a mode-`0600` environment file, and the three
`DRUMSCRIBE_DODO_LIVE_*` staged values. It creates a timestamped mode-`0600`
backup before atomically changing the active provider to Dodo `live_mode`.
Restart the API after promotion, verify readiness, and create only a no-charge
checkout session for the smoke test. A successful browser return never grants
credits; only a verified `payment.succeeded` webhook does.
