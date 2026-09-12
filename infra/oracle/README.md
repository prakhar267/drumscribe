# Oracle Always Free deployment

This deployment runs the public API, one CPU-only transcription worker, one
Celery Beat scheduler, and a Caddy TLS edge on a single Ampere A1 VM. PostgreSQL,
Redis, private object storage, email delivery, and error reporting remain managed
services and are configured through `/etc/drumscribe/drumscribe.env`.

The current Oracle Always Free Ampere allowance is 1,500 OCPU hours and 9,000 GB
hours monthly, equivalent to 2 OCPUs and 12 GB RAM across the tenancy. Keep the
sum of every A1 instance inside that allowance. The initial DrumScribe VM uses
1 OCPU and 6 GB RAM, plus a 46.6 GB boot volume inside the 200 GB Always Free
block-volume allowance.

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
public API and scheduler on the one-OCPU beta host. Keep Celery concurrency at
one; niceness protects responsiveness but does not make the free host suitable
for an advertised processing-time or availability SLA.

The measured 180-second production-equivalent probe took 34 minutes 16 seconds
on this shape and peaked at 3.70 GiB memory. Treat the instance as a constrained
beta host. Before resizing, inspect all tenancy A1 allocations and confirm the
new total remains inside the documented Always Free allowance; never select a
paid shape or attach a payment method without explicit approval.
