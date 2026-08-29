# DrumScribe implementation plan

This is the living delivery checklist for the production-oriented first release. A checked item means the code path exists and is covered by an automated or repeatable verification step; it does not imply that an ML model with unresolved commercial licensing is production-enabled.

## Phase 0 — foundation

- [x] Record architecture and product decisions.
- [x] Establish monorepo, source-control, formatting, and test conventions.
- [x] Verify runtime dependency and model licensing; keep unresolved models fail-closed.

## Phase 1 — platform

- [x] Next.js web application with typed API client.
- [x] FastAPI versioned REST API and OpenAPI schema.
- [x] PostgreSQL models and Alembic migrations.
- [x] Secure anonymous sessions and one-time email magic-link conversion.
- [x] Private S3-compatible storage and signed upload/download URLs.
- [x] Redis-backed, retryable worker jobs.

## Phase 2 — upload and projects

- [x] Drag/drop and file-picker upload with rights confirmation.
- [x] MIME plus FFprobe validation, configurable 150 MB / 12 minute limits.
- [x] Project dashboard, search, sort, rename, duplicate, and recoverable deletion.
- [x] Durable processing progress with friendly weighted stages.

## Phase 3–5 — music pipeline

- [x] Safe FFmpeg normalization and metadata capture.
- [x] Replaceable source-separation, transcription, beat tracking, quantization, and notation providers.
- [x] Commercial-safe production provider gate and clearly labelled local research provider.
- [x] Canonical drum-event model retaining raw and quantized timing.
- [x] MusicXML, MIDI, and PDF export from latest canonical events.
- [x] Rights-cleared deterministic synthetic demo and ground truth.

## Phase 6–9 — editor and practice

- [x] One authoritative audio transport shared by waveform, notation, grid, and playhead.
- [x] Editable drum grid: add, delete, drag, selection, copy/paste, velocity, zoom, and snap.
- [x] MusicXML/Verovio score rendering with playback and selection highlighting.
- [x] Command-based undo/redo, delta autosave, optimistic concurrency, and server snapshots.
- [x] Review-uncertain workflow, confidence strip, looping, speed, count-in, metronome, and mixer.
- [x] Keyboard shortcuts and accessible shortcut help.
- [x] Latest-revision asynchronous export workflow.

## Phase 10–12 — operations and quality

- [x] Protected, role-authorized admin/debug pipeline inspection.
- [x] ML benchmark CLI with JSON and HTML reports.
- [x] Structured logging, Sentry-compatible error/tracing hooks, and product events.
- [x] Dockerfiles and Compose for web/API/worker/beat/Postgres/Valkey/MinIO.
- [x] Unit, authorization, integration, Playwright UI, and real-stack acceptance tests.
- [x] CI for lint, typecheck, builds, tests, migrations, dependency scanning, and real-stack E2E.
- [x] Deployment, security, testing, evaluation, and local-development documentation.

## Acceptance run

- [ ] Upload a valid audio file through a signed private-storage URL.
- [ ] Leave/reopen while the job continues and reaches `READY`.
- [ ] Play synchronized audio, score, waveform, and drum grid.
- [ ] Loop four measures, switch to 0.5x, edit a snare, undo/redo, refresh, and retain the edit.
- [ ] Export current revision as MIDI, MusicXML, and readable PDF.
- [ ] Delete the project and verify every associated asset becomes inaccessible.
