# Testing

## Fast checks

```bash
pnpm lint
pnpm typecheck
pnpm test
uv run --project apps/api pytest
uv run --project packages/music-engine pytest
```

The web suite covers editing commands, transport/loop state, upload validation, and critical rendering. API tests cover authorization, transitions, bulk revisions, signed access, and validation contracts. Music-engine tests use deterministic synthetic fixtures for quantization and export semantics.

## Full acceptance

Start the Compose stack, then run `pnpm test:e2e`. The browser suite must exercise anonymous upload, progress recovery, editor playback, hit correction, undo/redo, autosave/reload, loop/rate controls, all three exports, and deletion. Tests must use generated audio only.

Before a release, additionally verify:

- FFprobe rejects a renamed text file and malformed/unsupported media.
- A file just above each byte/duration limit fails before expensive stages.
- A second user cannot enumerate or access any project-derived resource.
- Expired and post-deletion signed URLs fail.
- A worker retry resumes from the latest persisted successful stage.
- Reduced motion, keyboard-only navigation, focus visibility, and contrast on major screens.
- At least one current Chromium run at desktop and tablet widths.

## Visual QA

Playwright captures stable screenshots for the homepage, upload, progress, project library, editor, practice mode, export dialog, and admin diagnostics. Mask time-varying text and animations; review visual diffs rather than automatically accepting snapshots.

## GPU/research checks

Expensive source-separation and research-transcription checks do not run on every pull request. The optional workflow records environment, provider/model hash, dataset manifest hash, and benchmark artifacts. A passing GPU job does not authorize a model for commercial production.

