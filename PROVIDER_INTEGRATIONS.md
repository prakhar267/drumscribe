# Provider integrations

Last verified against public provider documentation: 2026-08-29. Public API shape is
not a substitute for account entitlement, executed commercial terms, a DPA, or legal
approval. DrumScribe requires all of those independently.

## Trust categories and selection

Every run is classified as one of:

- `PRODUCTION_COMMERCIAL` — contract-backed API or approved internally hosted model.
- `DEVELOPMENT_RESEARCH` — local research implementation with unresolved or unsuitable
  production rights.
- `TEST_FIXTURE` — deterministic fixture used only for tests and the labelled demo.

Production requires `DRUMSCRIBE_PIPELINE_PROVIDER=music_engine`, explicit commercial
approval, an approval reference, and only the concrete commercial providers listed
below. Startup fails instead of downgrading to a fixture.

## AudioShake drum-stem separation

Purpose: isolate the full drum stem from a private mix.

- API: `POST /assets`, `POST /tasks`, `GET /tasks/{id}`; target model defaults to
  `drums`, format `wav`.
- Credentials: `DRUMSCRIBE_AUDIOSHAKE_API_KEY` (`x-api-key`, server-side only).
- Account check: call the provider model-list endpoint and verify that the configured
  drum model is enabled before staging acceptance.
- Webhooks: the public docs support per-task `webhookUrl`, but do not document a
  verifiable signature. DrumScribe polls authenticated task state and does not trust
  an unsigned callback as completion authority.
- Timeout/retry: bounded by `DRUMSCRIBE_PROVIDER_TIMEOUT_SECONDS`; provider errors are
  normalized. Celery may retry transport-class failures at the orchestration layer.
- Idempotency: DrumScribe's durable processing job/stage checkpoint is the source of
  truth. The AudioShake API does not document an idempotency header for task creation;
  request IDs are persisted to prevent hidden duplicate accounting during diagnosis.
- Cost: task/target credits are persisted as `AudioShake credits`.
- Retention/privacy: exact input/output retention, regions, subprocessors, training
  use, deletion SLA, and output rights require contract confirmation.
- Fallback: none in production. A provider failure fails the job.
- Approval gate: key, contract reference, global approval reference, DPA/legal review,
  model entitlement, and rights-cleared quality/cost acceptance.

## Music AI workflow separation

Purpose: comparable alternative drum-stem provider without coupling the pipeline to a
vendor response.

- API: `GET /upload`, signed `PUT`, `POST /job`, `GET /job/{id}`.
- Credentials: `DRUMSCRIBE_MUSIC_AI_API_KEY` (`Authorization`, server-side only).
- Workflow: the exact workspace workflow slug and result key are configuration, not
  hard-coded assumptions. Staging must verify that it produces a full drum stem.
- Webhooks: polling is implemented because the public reference documents job polling;
  a callback is not used as an unauthenticated authority.
- Timeout/retry/idempotency: bounded polling, normalized errors, durable DrumScribe
  stage checkpoints, persisted provider job ID.
- Cost: public module pricing is informative only. Persisted cost remains null until
  the selected workflow response or contract supplies authoritative billing metadata.
- Retention/privacy: temporary-upload lifetime, result lifetime, regions,
  subprocessors, provider training use and deletion SLA require contract confirmation.
- Fallback: none in production.
- Approval gate: API key, exact workflow/result contract, contract reference,
  DPA/legal review and rights-cleared quality/cost acceptance.

## Klangio drum transcription

Purpose: convert the separated drum stem into raw, simultaneous, multi-label drum-hit
events. The adapter never generates notation directly.

- API: `POST /transcription?model=drums` with `outputs=json`, poll
  `GET /job/{id}/status`, fetch `GET /job/{id}/json`.
- Credentials: `DRUMSCRIBE_KLANGIO_API_KEY` (`kl-api-key`, server-side only).
- Validation: every result must contain canonicalizable hit rows with bounded onset,
  canonical instrument, velocity and confidence. Unsupported labels fail the run.
- Metadata: job ID, model, processing duration, deletion date, contract reference and
  sanitized response summary are persisted.
- Timeout/retry/idempotency: bounded authenticated polling and durable stage
  checkpoints. No consumer UI, scraping or consumer-product automation is used.
- Cost: null until account/API billing metadata or the contract supplies a reliable
  per-run amount.
- Retention/privacy: the API response deletion date is recorded; actual deletion,
  backups, regions, subprocessors, training use and output rights require contract
  confirmation.
- Fallback: none in production.
- Approval gate: API key with verified `drums` entitlement, contract/DPA/legal approval,
  output schema confirmation and rights-cleared quality/cost acceptance.

## Klangio beat/downbeat tracking

Purpose: produce canonical tempo segments, beat timestamps, downbeats and bar one.

- API: `POST /beat-tracking`, authenticated status polling and JSON fetch.
- Validation: at least two ordered beat times and an identified downbeat are required;
  tempo must be 20–400 BPM. Downbeat absence fails instead of inventing bar one.
- Metadata, timeout, retry, cost, privacy, fallback and approval rules match the
  Klangio drum provider above.

## Live tests

Normal CI uses mocked official request/response contracts and never spends provider
credits. Credentialed staging runs must set `RUN_LIVE_ML_TESTS=1`, use only
rights-cleared fixtures, name the provider request IDs, and delete remote inputs/jobs
when the provider API permits. Until credentials exist, the precise blocker is tracked
in `COMMERCIAL_DRUM_PROVIDER_BLOCKER.md`.
