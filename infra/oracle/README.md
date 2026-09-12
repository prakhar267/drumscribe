# Oracle Always Free deployment

This deployment runs the public API, one CPU-only transcription worker, one
Celery Beat scheduler, and a Caddy TLS edge on a single Ampere A1 VM. PostgreSQL,
Redis, private object storage, email delivery, and error reporting remain managed
services and are configured through `/etc/drumscribe/drumscribe.env`.

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

Only TCP 80/443 are publicly exposed by the stack. The API and worker stay on the
private Compose network, and the worker has no inbound port. Restrict SSH at both
the OCI network layer and the host firewall.

The worker starts through `nice -n 10` so model inference yields CPU time to the
public API and scheduler on the four-OCPU beta host. Keep Celery concurrency at
one until a sealed capacity run proves that greater concurrency preserves API
readiness; niceness protects responsiveness but does not make the free host
suitable for an advertised processing-time or availability SLA.

The 13 September 2026 180-second production-equivalent probe took 10 minutes 26
seconds on 4 OCPUs/24 GB: 9 minutes 41 seconds in HTDemucs-ft and 45 seconds in
recall fusion. It peaked at 3.74 GiB memory, produced 1,423 events, and kept
public readiness at HTTP 200. This fresh rights-cleared workload is equivalent
in duration and stages, but not identical in content, to the former
1-OCPU/6-GB probe that took 34 minutes 16 seconds. The result is a 3.28x speedup
and 69.6% wall-time reduction, but remains 3.48x slower than real time. Before
any later resize, inspect all tenancy A1 allocations and confirm the new total
remains inside the documented Always Free allowance; never select a paid shape
or attach a payment method without explicit approval.
