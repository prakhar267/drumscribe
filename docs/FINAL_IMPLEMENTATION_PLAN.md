# DrumScribe final implementation plan

This plan continues the existing architecture. It does not rebuild the application, replace working migrations, or introduce a second prototype. A completed code item is distinct from an external production approval: credentials, contracts, model/data rights and target-cloud configuration remain explicit launch gates.

## P0 — core product blocking

### P0.1 Production provider boundary

- [x] Replace ambiguous provider strings with explicit categories: `PRODUCTION_COMMERCIAL`, `DEVELOPMENT_RESEARCH`, `TEST_FIXTURE`.
- [x] Require provider identity, model/version, request ID, duration, confidence summary, normalized error, raw metadata, cost and retention metadata.
- [x] Make production startup reject fixture, mock, passthrough, non-commercial and unapproved research providers without fallback.
- [x] Keep fixture providers only for isolated tests and the explicitly labelled demo.
- [x] Add anti-fake tests proving different recordings cannot receive the same duration-derived output in a production-capable configuration.

### P0.2 Real source separation

- [x] Implement an HTTP commercial separation adapter with authenticated upload/reference input, status polling, timeout, retry/idempotency, output validation and private drum-stem ingestion.
- [ ] Support webhook verification when the selected provider offers it.
- [x] Normalize vendor output into a provider-neutral result and record latency/cost.
- [x] Add mocked contract tests and an opt-in live-provider test.
- [ ] Select a provider only after credentials, terms, retention and commercial approval are supplied.

### P0.3 Real drum transcription

- [x] Implement a provider-neutral commercial drum-transcription HTTP adapter.
- [x] Validate and normalize simultaneous multi-label hits, velocity and calibrated confidence into raw canonical hits.
- [x] Record provider request/model/cost/error metadata.
- [x] Add mocked contract tests and an opt-in rights-cleared live test.
- [x] If no real drum-specific commercial API is available, retain the fail-closed adapter contract and finish the self-hosted training path without pretending it is deployable.

### P0.4 Beat, bar and timing

- [x] Implement canonical tempo segments, beat/downbeat records and bar-one offset persistence.
- [x] Implement a production beat/downbeat adapter and opt-in live test.
- [x] Add API operations for set bar one, BPM/time signature changes, beat insert/delete/move, tempo changes, reset and requantization.
- [x] Preserve every raw drum onset while recomputing musical mapping.
- [x] Support 4/4, 3/4, 6/8 and 12/8 extremely well; retain arbitrary validated signatures.
- [x] Implement selective requantization with deliberate manual-edit preservation rules.

### P0.5 Real-song acceptance

- [ ] Run two legally usable, materially different recordings through the selected real providers.
- [ ] Verify the drum stem differs materially from the original and provider metadata is complete.
- [ ] Verify plausible audio-derived events, bounded timestamps, timing correction, synchronized editing, persistence and corrected exports.
- [ ] Do not mark P0 complete until the production-like journey uses no fixture provider.

## P1 — launch blocking

### P1.1 Quality and economics

- [ ] Build licensed benchmark manifests for clean stems and full mixes across the required genre/mix/timing conditions.
- [x] Add 25/50/100 ms onset metrics, separation metrics/listening rubric and provider-combination matrix.
- [x] Instrument correction burden: add/delete/move/reassign, tempo/bar corrections, correction minutes and corrections per audio minute.
- [x] Report quality, latency, processing seconds/audio minute, estimated cost/audio minute and cost/successful transcription.
- [ ] Establish a measured baseline; never invent an accuracy target.

### P1.2 ML lifecycle

- [x] Add configurable raw → validated → canonicalized → split → augmented → feature-cache stages.
- [x] Implement deterministic, realistic augmentation with manifest provenance.
- [x] Add configuration-driven training, resume/checkpoint, early stopping and metric logging.
- [x] Record experiment ID, Git commit, dataset version/hash, configuration and model hash.
- [x] Enforce licensing/attribution gates before any dataset or checkpoint becomes production eligible.

### P1.3 Product/editor architecture

- [x] Add explicit Edit, Timing, Review and Practice modes.
- [ ] Make notation readable, paginated/chunked and primary; preserve event selection and current-measure highlighting.
- [x] Build the Timing timeline and actions from P0.4.
- [ ] Build dedicated Review navigation, accept/delete/reassign/listen-around-note actions.
- [ ] Add contextual note and measure menus.
- [ ] Make the inspector contextual/collapsible and the transport/mixer denser and clearer.
- [x] Add useful error/not-found states and remove broad demo fallback on API 404s.

### P1.4 Production environment

- [ ] Deploy separate web, API and Celery worker/beat services.
- [ ] Provision isolated staging/production PostgreSQL, Valkey and private object storage.
- [ ] Configure production magic-link delivery, domain verification, SPF/DKIM, failure handling and environment-correct links.
- [ ] Configure TLS, secure cookies, trusted proxy handling, HSTS decision and exact CORS.
- [ ] Configure backups/PITR, retention/lifecycle/orphan cleanup and restore drills.
- [ ] Configure Sentry-compatible monitoring and documented alerts.
- [ ] Verify all migrations from zero against the target PostgreSQL release image.

### P1.5 Security, privacy and legal

- [ ] Threat-model each external provider and document audio transfer, retention, training use and deletion behavior.
- [ ] Obtain explicit commercial approval for code, weights, datasets and contracts.
- [ ] Complete legal review of Privacy, Terms and Copyright policy.
- [ ] Run authorization, signed-URL, media-parser, rate-limit, secret-redaction and deletion tests against staging.

## P2 — important polish

- [ ] Redesign the homepage around the live synchronized product proof and remove clipped/unsupported claims.
- [ ] Refine upload, processing, library, auth, settings and admin hierarchy using documented tokens/components.
- [ ] Add polished editor modes, compact mixer mutes, snapping preview and clearer bar/beat/hit states.
- [ ] Add Practice speed presets, arbitrary speed and loop-count-based auto speed progression.
- [ ] Complete mobile practice/review/basic-correction flows and tablet layouts.
- [ ] Verify visible focus, keyboard menus/dialogs, non-color states, reduced motion and supplementary notation text.
- [ ] Benchmark 30-second, 3-, 6- and 12-minute projects and thousands of events; optimize only measured bottlenecks.
- [ ] Run Chromium, Firefox and WebKit desktop/tablet/mobile coverage, including Safari audio constraints.
- [ ] Capture and manually inspect every required screen at 1440×900, 1280×832, 1024×768, 768×1024 and 390×844.

## P3 — post-launch

- [ ] Performance recording/comparison interfaces and real timing feedback; never infer success from loop count.
- [ ] Expanded cymbal/articulation taxonomy where labelled data supports it.
- [ ] PNG, MEI and DAW-specific exports.
- [ ] Optional Google authentication after privacy, transfer and support implications are reviewed.
- [ ] Foldering/sharing/collaboration only after private-project defaults remain safe.
- [ ] Payments, subscriptions and quota monetization only as a separate future project.

## Required documentation outputs

- [x] `docs/COMPLETION_AUDIT.md`
- [x] `docs/FINAL_IMPLEMENTATION_PLAN.md`
- [ ] `docs/DESIGN_SYSTEM.md`
- [x] `PROVIDER_INTEGRATIONS.md`
- [x] `OPERATIONS.md`
- [x] `INCIDENT_RESPONSE.md`
- [x] `DATA_RETENTION.md`
- [x] `LAUNCH_CHECKLIST.md`
- [x] Update README, architecture, licensing, evaluation, deployment, security and testing documents.

## Local and hosted release gates

- [x] Provide `./scripts/ci.sh` and `make ci` parity for formatting, lint, typing, unit/integration tests, build, migrations and dependency audits.
- [x] Keep GitHub workflows aligned with the local command.
- [ ] Resolve the owner account’s GitHub billing/spending-limit block, then rerun hosted CI.
- [x] Require opt-in `RUN_LIVE_ML_TESTS=1` for credentialed provider tests.
- [ ] Require a staging acceptance record naming real provider requests/model versions before launch.

## Stop conditions

The repository must not claim launch completion while any of these are true:

- A production-capable path can select deterministic, mock, passthrough or unapproved research providers.
- No real provider credentials and commercial/legal approval are available.
- The real-song benchmark has no measured result.
- Timing/bar correction cannot be completed and persisted.
- Corrected MIDI, MusicXML and PDF exports have not passed real-song staging acceptance.
- Deletion does not revoke all previously issued private URLs.
- Legal documents or provider data-handling terms remain unapproved.
