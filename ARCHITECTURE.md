# DrumScribe architecture

## System shape

DrumScribe is a modular monorepo with four production process roles:

- `apps/web`: Next.js App Router UI. It owns presentation and local editing commands, but never the canonical persisted transcription.
- `apps/api`: FastAPI REST API. It owns authorization, projects, sessions, revisions, upload/export URLs, and the canonical event schema.
- `apps/worker`: a Redis-backed Python worker entrypoint sharing the API's pipeline service layer. Stages are checkpointed so retries resume at the failed boundary.
- Celery Beat: one scheduler instance for retention and durable cleanup tasks.

PostgreSQL is the source of truth, Redis provides queue/coordination, and S3-compatible private object storage contains originals, normalized files, stems, waveform peaks, and exports. Browser access uses short-lived signed URLs only.

## Critical boundaries

1. **Canonical events, never rendered output.** `DrumEvent` records raw onset, readable quantized position, instrument, velocity, confidence, provenance, and manual-edit state. MusicXML/SVG, MIDI, PDF, and the grid are projections.
2. **Replaceable audio intelligence.** Normalization, separation, drum transcription, beat tracking, quantization, and notation are protocols. Provider licensing and readiness are runtime configuration, not UI assumptions.
3. **One transport clock.** The HTML audio element is the authority. A transport store publishes current time, rate, loop, and mixer state to every visualization on animation frames.
4. **Bulk, revisioned editing.** The client applies commands optimistically and autosaves compact batches. The API authorizes the project, applies a transaction, and periodically stores restorable snapshots.
5. **Private and deletable.** Opaque IDs, ownership checks, signed object URLs, log redaction, explicit upload-rights confirmation, opt-in model-improvement consent, and background asset purging are defaults.
6. **Raw time is immutable.** A canonical timing map stores tempo segments,
   beat/downbeat positions, meter and bar one separately from raw drum onset
   seconds. Timing edits selectively remap musical positions and regenerate
   notation without rerunning expensive providers.
7. **Measured provider provenance.** Every provider run records category,
   provider/model/request identity, latency, confidence summary, normalized
   failure, raw metadata, cost, retention and contract reference. Production
   configuration fails closed unless every selected provider is commercially
   approved.

## API contract

The versioned API lives under `/api/v1` and exposes sessions, projects, upload completion, processing jobs, canonical events, timing maps, bulk edits, revisions, exports, deletion, account controls, and admin diagnostics. State-changing retryable operations accept idempotency keys. Event/timing writes use independent optimistic versions.

## Local and production modes

Local Compose supplies PostgreSQL, Valkey, MinIO, API, worker/scheduler, and web.
Its deterministic pipeline is labelled test/development infrastructure and is
rejected by production settings. Production-capable adapters exist for AudioShake
or Music AI separation and Klangio drum transcription/beat tracking, but remain
blocked until credentials and contract approval are supplied. `ml/` contains the
separate licensed-manifest, preparation, training, calibration and evaluation
lifecycle; it ships no production-approved checkpoint.

## Deferred by design

Payments, public sharing/catalogues, automated use of customer audio for training, performance coaching, and unusual-meter claims are deliberately absent. Entitlement and feature-flag interfaces preserve clean extension points.
