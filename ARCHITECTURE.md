# DrumScribe architecture

## System shape

DrumScribe is a modular monorepo with three deployable processes:

- `apps/web`: Next.js App Router UI. It owns presentation and local editing commands, but never the canonical persisted transcription.
- `apps/api`: FastAPI REST API. It owns authorization, projects, sessions, revisions, upload/export URLs, and the canonical event schema.
- `apps/worker`: a Redis-backed Python worker entrypoint sharing the API's pipeline service layer. Stages are checkpointed so retries resume at the failed boundary.

PostgreSQL is the source of truth, Redis provides queue/coordination, and S3-compatible private object storage contains originals, normalized files, stems, waveform peaks, and exports. Browser access uses short-lived signed URLs only.

## Critical boundaries

1. **Canonical events, never rendered output.** `DrumEvent` records raw onset, readable quantized position, instrument, velocity, confidence, provenance, and manual-edit state. MusicXML/SVG, MIDI, PDF, and the grid are projections.
2. **Replaceable audio intelligence.** Normalization, separation, drum transcription, beat tracking, quantization, and notation are protocols. Provider licensing and readiness are runtime configuration, not UI assumptions.
3. **One transport clock.** The HTML audio element is the authority. A transport store publishes current time, rate, loop, and mixer state to every visualization on animation frames.
4. **Bulk, revisioned editing.** The client applies commands optimistically and autosaves compact batches. The API authorizes the project, applies a transaction, and periodically stores restorable snapshots.
5. **Private and deletable.** Opaque IDs, ownership checks, signed object URLs, log redaction, explicit upload-rights confirmation, opt-in model-improvement consent, and background asset purging are defaults.

## API contract

The versioned API lives under `/api/v1` and exposes sessions, projects, upload completion, processing jobs, canonical events, bulk edits, revisions, exports, deletion, account controls, and admin diagnostics. State-changing retryable operations accept idempotency keys.

## Local and production modes

Local Compose supplies PostgreSQL, Redis, MinIO, API, worker, and web. A deterministic development pipeline produces a useful editable first draft without external credentials. Optional Demucs/research transcription dependencies are isolated behind extras and must never be enabled in production when `MODEL_LICENSING.md` marks them non-commercial or unresolved.

## Deferred by design

Payments, public sharing/catalogues, automated use of customer audio for training, performance coaching, and unusual-meter claims are deliberately absent. Entitlement and feature-flag interfaces preserve clean extension points.
