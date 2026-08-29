# DrumScribe implementation plan

This is the living delivery checklist for the production-oriented first release. A checked item means the code path exists and is covered by an automated or repeatable verification step; it does not imply that an ML model with unresolved commercial licensing is production-enabled.

## Phase 0 — foundation

- [x] Record architecture and product decisions.
- [x] Establish monorepo, source-control, formatting, and test conventions.
- [ ] Verify runtime dependency and model licensing.

## Phase 1 — platform

- [ ] Next.js web application with typed API client.
- [ ] FastAPI versioned REST API and OpenAPI schema.
- [ ] PostgreSQL models and Alembic migrations.
- [ ] Secure anonymous/session authentication and optional Google/email adapters.
- [ ] Private S3-compatible storage and signed upload/download URLs.
- [ ] Redis-backed, retryable worker jobs.

## Phase 2 — upload and projects

- [ ] Drag/drop and file-picker upload with rights confirmation.
- [ ] MIME plus FFprobe validation, configurable 150 MB / 12 minute limits.
- [ ] Project dashboard, search, sort, rename, duplicate, and recoverable deletion.
- [ ] Durable processing progress with friendly weighted stages.

## Phase 3–5 — music pipeline

- [ ] Safe FFmpeg normalization and metadata capture.
- [ ] Replaceable source-separation, transcription, beat tracking, quantization, and notation providers.
- [ ] Commercial-safe production provider gate and clearly labelled local research provider.
- [ ] Canonical drum-event model retaining raw and quantized timing.
- [ ] MusicXML, MIDI, and PDF export from latest canonical events.
- [ ] Rights-cleared deterministic synthetic demo and ground truth.

## Phase 6–9 — editor and practice

- [ ] One authoritative audio transport shared by waveform, notation, grid, and playhead.
- [ ] Editable drum grid: add, delete, drag, selection, copy/paste, velocity, zoom, and snap.
- [ ] Score rendering with playback and selection highlighting.
- [ ] Command-based undo/redo, debounced autosave, and server snapshots.
- [ ] Review-uncertain workflow, confidence strip, looping, speed, count-in, metronome, and mixer.
- [ ] Keyboard shortcuts and accessible shortcut help.
- [ ] Latest-revision asynchronous export workflow.

## Phase 10–12 — operations and quality

- [ ] Protected admin/debug pipeline inspection.
- [ ] ML benchmark CLI with JSON and HTML reports.
- [ ] Structured logging, error monitoring hooks, OpenTelemetry hooks, and product events.
- [ ] Dockerfiles and Compose for web/API/worker/Postgres/Redis/MinIO.
- [ ] Unit, authorization, integration, Playwright E2E, and visual smoke tests.
- [ ] CI for lint, typecheck, builds, tests, migrations, and dependency scanning.
- [ ] Deployment, security, testing, evaluation, and local-development documentation.

## Acceptance run

- [ ] Upload a valid audio file through a signed private-storage URL.
- [ ] Leave/reopen while the job continues and reaches `READY`.
- [ ] Play synchronized audio, score, waveform, and drum grid.
- [ ] Loop four measures, switch to 0.5x, edit a snare, undo/redo, refresh, and retain the edit.
- [ ] Export current revision as MIDI, MusicXML, and readable PDF.
- [ ] Delete the project and verify every associated asset becomes inaccessible.

