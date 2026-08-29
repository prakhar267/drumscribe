# DrumScribe completion audit

Audit date: 2026-08-29

Audited revision: `513b15d`

Audit environment: macOS, Node.js 23.11, pnpm 11.19, Python 3.12 through `uv`, Next.js development server, FastAPI/Uvicorn, fresh SQLite database, local signed-file storage, inline development queue.

This audit is evidence from the running repository, not a filename review. The current UI was exercised through the in-app browser at 1440×900. A rights-cleared generated WAV was uploaded through the browser, processed through the real API/storage/job orchestration, and opened in the editor. The development provider output and database provider records were inspected directly.

## Baseline verification

| Check | Result |
| --- | --- |
| Web lint | Passed |
| Web TypeScript | Passed |
| Web unit tests | 20 passed |
| Next.js production build | Passed; 13 routes generated |
| API Ruff check and format check | Passed |
| API mypy | Passed; 39 source files |
| API tests | 38 passed |
| Music-engine tests | 41 passed |
| ML workspace tests | 9 passed |
| Clean-database migration | `6153412384df -> d90d268d92dc` passed |
| Alembic drift check | No new upgrade operations detected |
| Compose configuration | Passed |
| Manual private upload-to-editor flow | Passed with the development-only provider |

The browser-flow output was not a real transcription. Its database record explicitly reported:

```text
separation: passthrough-development/1
transcription: deterministic-development/1
beatTracking: mock-beat-tracker
```

The generated output was a fixed 120 BPM kick/snare/closed-hi-hat pattern at exact 250 ms intervals. This confirms the core defect described in the takeover brief.

## Current UI evidence

1. [Homepage](audit/current-ui/01-homepage.png) — strong identity and hierarchy; primary navigation CTA clips at the right edge in the audited viewport and the core interactive product is below the first fold.
2. [Upload](audit/current-ui/02-upload.png) — clear rights confirmation, limits, privacy and file choice; lower action content sits below the viewport.
3. [Projects](audit/current-ui/03-projects.png) — visually music-oriented cards; the accessibility tree briefly announces “No matching projects” while client demo projects hydrate.
4. [Editor idle](audit/current-ui/04-editor-idle.png) — complete editing surface; twelve measures are compressed into one tiny notation strip and the empty inspector permanently consumes width.
5. [Editor selected note](audit/current-ui/05-editor-selected-note.png) — functional instrument/velocity/confidence inspector; editing modes and contextual actions are absent.
6. [Editor playing](audit/current-ui/06-editor-playing.png) — score, waveform and grid playheads visibly move from the shared transport.
7. [Practice](audit/current-ui/07-practice.png) — focused controls exist; the score uses a small strip at the top of a very large empty notation surface.
8. [Processing](audit/current-ui/08-processing.png) — clear weighted stages and leave-page reassurance; no source waveform, duration or elapsed context.
9. [Project settings](audit/current-ui/09-project-settings.png) — project metadata and revision/delete surfaces work; timing is explicitly read-only.
10. [Account settings](audit/current-ui/10-account-settings.png) — account conversion, consent, data export and deletion controls exist.
11. [Authentication](audit/current-ui/11-auth.png) — polished passwordless entry with anonymous-project continuity copy.
12. [Admin locked state](audit/current-ui/12-admin.png) — correctly fails closed without the server-side admin key.
13. [Unknown project defect](audit/current-ui/13-error-state.png) — an invalid project ID silently opens the demo editor instead of an error state.
14. [Development pipeline output](audit/current-ui/14-real-flow-development-output.png) — actual private upload/API orchestration succeeded, but the visible exact-grid pattern confirms deterministic fake transcription.

Screenshot evidence establishes visible behavior and layout only. It does not establish WCAG conformance, screen-reader behavior, provider quality, browser audio timing, or production infrastructure health.

## WORKING

- Responsive Next.js product surfaces: homepage, upload, processing, projects, editor, practice, authentication, project/account settings, legal and protected admin states.
- Anonymous session creation and one-time email magic-link conversion without losing anonymous projects.
- Typed FastAPI v1 API, owner-scoped authorization, private storage, signed upload/download URLs and opaque object keys.
- FFprobe validation, configurable upload limits, safe FFmpeg argv handling, normalization, waveform peak generation and metadata capture.
- Durable processing-stage model with cancellation, retry, idempotency, checkpoints, structured error codes and Celery support.
- PostgreSQL-oriented SQLAlchemy schema and Alembic migrations, including users, sessions, projects, assets, jobs, model runs, transcriptions, canonical events, revisions, exports, feedback, audit events and product events.
- Canonical 13-instrument drum taxonomy with General MIDI mappings, raw and quantized timing, confidence, provenance and manual-edit state.
- Verovio MusicXML engraving with stable canonical-event selection mapping.
- Drum grid add/delete/drag, vertical reassignment, box selection, multi-select, copy/paste, duplication, velocity editing, snap modes, confidence overlay and zoom.
- Shared audio transport, waveform seek/loop, notation/grid playheads, speed control, pitch-preservation request, metronome, count-in and original/drum mixer.
- Delta autosave with optimistic concurrency, undo/redo and server revision snapshots/restoration.
- Asynchronous MIDI, MusicXML and PDF exports from the current saved revision.
- Recoverable project deletion, account deletion, retention jobs and revocation/reissue of signed audio and export URLs.
- Redis/Valkey-backed distributed rate limits and distinct liveness/readiness checks.
- Structured logs, Sentry-compatible hooks, protected job diagnostics and product/audit event storage.
- Leakage-safe dataset manifests, canonical label mapping and benchmark JSON/HTML metrics.
- Dockerfiles, local Compose topology, CI workflows, dependency scanning and release documentation.

## PARTIALLY WORKING

- Provider metadata: provider names, versions, stage durations and raw hit summaries are recorded, but request IDs, normalized error categories, cost fields, provider retention metadata and per-stage commercial billing are not first-class fields.
- Tempo support: the music engine supports piecewise tempo maps and time-signature changes, and exports have compound-meter/variable-tempo tests. The web transport and editor still operate from one project BPM and numerator.
- Review workflow: low-confidence navigation and editing work, but there is no dedicated Review mode, accept/mark-correct action, listen-around-note action or visual error-comparison layer.
- Admin diagnostics: job timing, assets, provider versions and model-run summaries are visible. Stage-specific reprocessing and dedicated raw-versus-quantized inspection are missing.
- Product analytics: upload, processing start, corrections and export downloads are recorded. Editor-open, practice usage, correction-time, bar/timing corrections, provider cost and minutes-saved metrics are incomplete.
- ML workspace: manifests, split protection, label mapping and evaluation exist. Preparation, augmentation, feature caching, training, checkpointing and experiment tracking do not.
- Cross-browser coverage: Chromium browser behavior and responsive baselines exist. Firefox, WebKit, tablet matrix, Safari audio restrictions and background-tab behavior are not verified.
- Performance: precomputed waveform peaks and batched autosave are implemented. No committed 30-second/3/6/12-minute performance report or thousands-of-events browser budget exists.

## FAKE / MOCKED

- The development source separator copies the original recording byte-for-byte to the drum-stem destination.
- The development transcriber ignores audio content and emits a deterministic 120 BPM rock pattern based only on duration.
- The development beat tracker always returns a constant 120 BPM 4/4 map.
- The frontend demo is intentionally synthetic and valid only as a product tour/test fixture.
- Existing normal CI provider tests use fixtures. There is no opt-in live commercial-provider test.

These paths are acceptable only for test fixtures and clearly labelled offline demos. They cannot be selectable in a production-capable environment.

## BROKEN

- Any API 404 is currently treated as “demo unavailable” by the browser client. An unknown project ID therefore renders the demo project rather than a not-found/error state.
- The running full upload journey produces a convincing-looking but unrelated chart because development transcription is duration-derived rather than audio-derived.
- The current UI copy says DrumScribe “isolates the drums” without a visible development-mode qualification on the upload and processing surfaces.

## MISSING

- A production-approved source-separation adapter with authenticated request, polling/webhook, result download, timeout/retry/idempotency, latency and cost capture.
- A production-approved drum-transcription adapter or a trained, commercially licensed self-hosted checkpoint.
- A production-approved beat/downbeat provider with canonical beats, downbeats, bar one and tempo segments.
- Live-provider opt-in tests and the required anti-fake regression using two materially different recordings.
- Legally usable real-song separation and transcription benchmark corpora and actual benchmark reports.
- SI-SDR or comparable objective separation evaluation when stem ground truth is available, plus structured listening notes otherwise.
- Correction-burden instrumentation and provider quality/latency/cost matrix reporting.
- Manual Timing mode: set bar one, tap/type BPM, edit time signature, drag/insert/delete beats, tempo changes, reset and selective requantization.
- Dataset validation/canonicalization stages, deterministic audio augmentation, feature caching, configuration-driven training, resume/checkpoint/early-stop, experiment IDs and model hashes.
- Dedicated editor Edit/Timing/Practice/Review mode architecture and contextual hit/measure menus.
- Auto speed progression in Practice mode.
- Production magic-link vendor integration and failure telemetry.
- Production deployment instance, domain/TLS, managed database/queue/storage, backups, monitoring dashboards and alerting.
- Operations, incident-response, data-retention, provider-integration, design-system and final launch-checklist documents requested by the takeover brief.
- Local one-command CI parity script.

## NEEDS REDESIGN

- The editor needs explicit modes so note editing, timing correction, review and practice do not compete in one layout.
- Notation must become the primary artifact with paginated/chunked readable measures rather than a single compressed horizontal score.
- The inspector should be contextual/collapsible instead of reserving width when no note is selected.
- Practice notation needs a readable scale and much better use of the available canvas.
- The transport/mixer needs compact mute/volume/count-in affordances and clearer professional grouping.
- Waveform and grid need stronger bar hierarchy, synchronized selected ranges and scalable long-song behavior.
- The homepage first viewport should show the live product proof without clipping or relying on claims.
- Processing should include recording identity, duration/waveform context and transparent provider status without fake precision.
- The project-library loading/empty states need to avoid contradictory announcements.
- Mobile needs a deliberate practice/review experience rather than compressed desktop editing.

## NEEDS PRODUCTION CREDENTIALS

- Commercial source-separation API account, approved contract, API credentials and verified retention/training policy.
- Commercial drum-transcription API access if a real drum-specific endpoint is available; otherwise an approved self-hosted model checkpoint and deployment environment.
- Commercial beat/downbeat API credentials if used.
- Private production object-storage credentials and bucket/domain configuration.
- Managed PostgreSQL and Redis/Valkey credentials.
- Production magic-link email/webhook provider, verified sending domain and secret.
- Sentry/telemetry project configuration.
- Hosting, TLS/domain and secret-manager access.
- GitHub billing/spending-limit resolution so hosted Actions can start.
- Qualified legal approval for provider contracts, model/data licensing and customer-facing legal documents.

## Completion verdict

The repository is a substantial, well-tested product platform and editor. It is not launchable as an AI transcription product because the core audio intelligence is still fake in the only credential-free execution path, no commercial provider is implemented, no real quality baseline exists, and timing correction is absent. Production must continue to fail closed until those gates are satisfied.
