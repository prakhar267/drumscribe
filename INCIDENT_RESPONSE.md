# Incident response

## Severity

- **SEV-1:** confirmed unauthorized media/account access, destructive data loss,
  leaked production secret, or broad outage of upload/playback/export.
- **SEV-2:** material processing corruption, provider privacy breach, retention
  backlog, sustained queue failure, or elevated cross-user authorization errors.
- **SEV-3:** isolated job/provider failures or degraded non-core functionality.

## First 30 minutes

1. Name an incident lead, start a private timeline and preserve request/job IDs.
2. Contain: disable affected credentials/provider, stop new jobs or remove the
   affected service from traffic. Do not delete evidence.
3. Verify scope from audit events, provider request IDs, object-access logs and
   deployment changes. Never copy customer audio into the incident record.
4. For secret exposure, revoke/rotate at the issuer and invalidate dependent
   sessions or signed access. For authorization risk, disable the route or service
   until an ownership test passes.
5. Engage provider/security/legal contacts when customer data may have left the
   documented processing boundary.

## Recovery and review

Deploy a reviewed fix, migrate only forward, test one synthetic and one authorized
staging project, verify private URL revocation, then restore traffic gradually.
Reconcile queued jobs idempotently and record which provider/model versions were
affected. Do not silently replace failed real processing with fixture output.

Customer/regulatory notification decisions require the owner and counsel. Within
five business days, document impact, root cause, detection gap, containment,
recovery, data/provider scope and owners/dates for preventive work. Convert the
failure into an automated test or alert where practical.

Before launch, replace the placeholder security contact in project legal copy
with a monitored address and publish coordinated-disclosure guidance.
