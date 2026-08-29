# Launch checklist

An unchecked external gate is a launch blocker, not permission to substitute
fixture output.

## Core product

- [ ] AudioShake or Music AI credentials, exact workflow/model and signed commercial/DPA approval recorded.
- [ ] Klangio drum and beat API access, credentials and signed commercial/DPA approval recorded.
- [ ] Provider retention, model-training use, regions, subprocessors, output rights and deletion behavior approved.
- [ ] Two materially different rights-cleared songs pass separation, transcription, timing, synchronized editing and corrected MIDI/MusicXML/PDF export.
- [ ] The required separation and clean/full-mix corpora produce non-synthetic HTML/JSON reports.
- [ ] Correction burden establishes a measured baseline; no accuracy or time-saved claim is invented.

## Infrastructure

- [ ] Separate web/API/worker/scheduler services deployed to staging and production.
- [ ] Managed PostgreSQL PITR, Valkey durability and private encrypted object storage configured.
- [ ] Exact CORS/host allowlists, secure cookies, TLS, one-year HSTS and trusted proxies verified.
- [ ] Production email domain, SPF/DKIM, bounce handling and environment-correct links verified.
- [ ] Error, queue, provider and cost alerts plus an on-call contact configured.
- [ ] Backup restore, deleted-data replay, retention and orphan-cleanup drills completed.

## Security, legal and quality

- [ ] Legal review signs Privacy, Terms, Copyright, provider transfer and retention statements.
- [ ] Production security contact and coordinated disclosure route are monitored.
- [ ] Authorization, signed-URL, malicious media, limit, redaction, deletion and account-conversion tests pass against staging.
- [ ] `make ci` and hosted CI pass; the owner's GitHub billing/spending restriction is resolved.
- [ ] Required desktop/tablet/mobile screenshots pass manual design/accessibility review.
- [ ] Chromium, Firefox, WebKit and Safari audio-gesture behavior pass.
- [ ] 30-second, 3-, 6- and 12-minute projects pass measured performance budgets.

## Release record

Record release commit, migration revision, provider/model versions, acceptance
provider request IDs, benchmark hashes, image digests, configuration approval,
rollback owner and final go/no-go decision.
