# Testing

## Fast checks

```bash
pnpm lint
pnpm typecheck
pnpm test
uv run --project apps/api pytest apps/api/tests
uv run --project packages/music-engine pytest packages/music-engine/tests
uv run --project ml pytest ml/tests
```

The web suite covers editing commands, transport/loop state, upload validation, and critical rendering. API tests cover authorization, transitions, bulk revisions, signed access, and validation contracts. Music-engine tests use deterministic synthetic fixtures for quantization and export semantics.

## Full acceptance

The normal `pnpm test:e2e` suite runs deterministic desktop/mobile UI tests without external services. The release acceptance path uses the actual PostgreSQL, Valkey, MinIO, API, Celery worker, FFmpeg pipeline, and production web build:

```bash
docker compose up --detach --build --wait --wait-timeout 180
pnpm test:e2e:stack
```

`full-stack.spec.ts` exercises direct private upload from the browser, anonymous-to-email ownership conversion, background processing, editor playback and correction, undo/redo, serialized autosave plus reload, loop/rate controls, semantic MIDI/MusicXML/PDF downloads, project deletion, and revocation of a previously issued audio URL. It generates its own rights-cleared WAV fixture.

Before a release, additionally verify:

- FFprobe rejects a renamed text file and malformed/unsupported media.
- A file just above each byte/duration limit fails before expensive stages.
- A second user cannot enumerate or access any project-derived resource.
- Expired and post-deletion signed URLs fail.
- A worker retry resumes from the latest persisted successful stage.
- Reduced motion, keyboard-only navigation, focus visibility, and contrast on major screens.
- At least one current Chromium run at desktop and tablet widths.

## Visual QA

The browser suite checks the major homepage, upload, progress, editor, notation, and mobile states. Before a visual baseline is accepted or updated, capture the homepage, upload, progress, project library, editor, practice mode, export dialog, and populated admin diagnostics at fixed viewports; mask time-varying text and animations and review the rendered diff rather than accepting it automatically.

## GPU/research checks

Expensive source-separation and research-transcription checks do not run on every pull request. The optional workflow records environment, provider/model hash, dataset manifest hash, and benchmark artifacts. A passing GPU job does not authorize a model for commercial production.
