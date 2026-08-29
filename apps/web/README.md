# DrumScribe web

The Next.js product surface for DrumScribe. The app is fully navigable in deterministic demo mode and switches to the versioned service API when it is available.

```bash
pnpm install --frozen-lockfile
pnpm dev
```

Open `http://localhost:3000`, choose **Try the demo**, and edit the bundled synthetic transcription. No credentials or copyrighted audio are required.

## Verification

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
```

The local pnpm workspace allowlists build scripts only for the exact reviewed `sharp@0.34.5` and `unrs-resolver@1.12.2` releases.

Copy `.env.example` to `.env.local` to override upload limits or connect the API. `NEXT_PUBLIC_DEMO_MODE=true` enables local fallbacks only when the API cannot be reached. The admin screen is server-protected and stays locked until `ADMIN_UI_KEY` is configured.

## Frontend boundaries

- `lib/domain.ts` is the canonical event/tempo/project model.
- `lib/api/client.ts` is the only browser-side persistence boundary and uses bulk event writes.
- `components/transport-provider.tsx` owns the single authoritative `HTMLAudioElement` clock.
- `components/editor/` owns interaction and rendering; notation is a semantic, accessible renderer that can be replaced by a lazy Verovio adapter without changing canonical events.
- Browser storage is a deliberate offline/demo fallback, not the production data authority.
