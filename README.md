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
uv run --project apps/api pytest
uv run --project apps/api uvicorn drumscribe_api.main:app --reload --port 8000

# Music engine
uv sync --project packages/music-engine --all-extras
uv run --project packages/music-engine pytest
```

The implementation checklist is in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and the architecture rationale is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Safety and legal status

- Uploaded audio is private, access-controlled, and intended for material the uploader has the right to process.
- Customer audio is never used for model training without explicit opt-in consent; the default is false.
- No streaming-service downloader or public chart catalogue is included.
- Legal pages are launch-ready placeholders only and require review by qualified counsel before public release.
- No payment integration is present. Every account receives the internal `FREE_BETA` entitlement.

See [SECURITY.md](SECURITY.md), [MODEL_LICENSING.md](MODEL_LICENSING.md), and [DEPLOYMENT.md](DEPLOYMENT.md) before exposing an environment publicly.

