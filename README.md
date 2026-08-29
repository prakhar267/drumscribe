# DrumScribe

DrumScribe turns an uploaded song into an editable drum chart, keeps its waveform, drum events, and notation synchronized, and supports practice plus MIDI, MusicXML, and PDF export.

This repository is a production-oriented first release, not a claim of perfect automatic transcription. The default development provider creates an editable first draft without commercial model credentials. Any research model is isolated and blocked from production unless its complete code, weights, data, and commercial-use status are explicitly approved in `MODEL_LICENSING.md`.

## Quick start

Prerequisites: Docker Desktop, Node.js 22+, pnpm, and `uv`. Native FFmpeg is only required when running the API/worker outside Docker.

```bash
cp .env.example .env
docker compose up --build
```

Open <http://localhost:3000>. MinIO's local console is available at <http://localhost:9001>; the bucket is private and application downloads are signed.

The stack runs a deterministic, explicitly development-only transcription
provider so a fresh clone can exercise signed upload, queued FFmpeg processing,
editing, exports, and revocable deletion without third-party credentials. It is
not presented as a commercially deployable ML model.

For a faster frontend-only product tour:

```bash
pnpm install
pnpm dev
```

The homepage demo and editor fallback are deterministic and require no uploaded music or third-party credentials.

## Developer workflow

```bash
# Web
pnpm install
pnpm dev
pnpm lint
pnpm typecheck
pnpm test
pnpm build

# API
uv sync --project apps/api --all-extras
uv run --project apps/api alembic upgrade head
uv run --project apps/api pytest apps/api/tests
uv run --project apps/api uvicorn drumscribe_api.main:app --reload --port 8000

# Music engine
uv sync --project packages/music-engine --extra pdf --group dev
uv run --project packages/music-engine pytest packages/music-engine/tests
uv sync --project ml --all-extras
uv run --project ml pytest ml/tests
```

Generate a rights-cleared audio/MIDI/ground-truth fixture with:

```bash
uv run --project packages/music-engine drumscribe-synthetic ./tmp/synthetic-demo --bars 4
```

Run the real browser/API/worker/PostgreSQL/Valkey/MinIO acceptance path after the
Compose stack is healthy:

```bash
pnpm install --frozen-lockfile
docker compose up --detach --build --wait --wait-timeout 180
pnpm test:e2e:stack
```

The implementation checklist is in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and the architecture rationale is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Safety and legal status

- Uploaded audio is private, access-controlled, and intended for material the uploader has the right to process.
- Customer audio is never used for model training without explicit opt-in consent; the default is false.
- No streaming-service downloader or public chart catalogue is included.
- Legal pages are launch-ready placeholders only and require review by qualified counsel before public release.
- No payment integration is present. Every account receives the internal `FREE_BETA` entitlement.

See [SECURITY.md](SECURITY.md), [MODEL_LICENSING.md](MODEL_LICENSING.md), and [DEPLOYMENT.md](DEPLOYMENT.md) before exposing an environment publicly.
Third-party runtime obligations are recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
