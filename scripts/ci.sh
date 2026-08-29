#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

pnpm --filter @drumscribe/web lint
pnpm --filter @drumscribe/web typecheck
pnpm --filter @drumscribe/web test
pnpm --filter @drumscribe/web build

uv sync --project packages/music-engine --extra pdf --group dev --locked
uv run --project packages/music-engine ruff format --check packages/music-engine/src packages/music-engine/tests
uv run --project packages/music-engine ruff check packages/music-engine/src packages/music-engine/tests
uv run --project packages/music-engine pytest packages/music-engine/tests

uv sync --project ml --extra dev --locked
uv run --project ml ruff format --check ml/src ml/tests
uv run --project ml ruff check ml/src ml/tests
uv run --project ml pytest ml/tests

uv sync --project apps/api --all-extras --dev --locked
uv run --project apps/api ruff format --check apps/api/src apps/api/tests
uv run --project apps/api ruff check apps/api/src apps/api/tests
uv run --project apps/api mypy apps/api/src
uv run --project apps/api pytest apps/api/tests

migration_dir="$(mktemp -d)"
trap 'rm -rf "$migration_dir"' EXIT
export DRUMSCRIBE_DATABASE_URL="sqlite+aiosqlite:///$migration_dir/migration-check.sqlite3"
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini check

docker compose config --quiet

if [[ "${DRUMSCRIBE_SKIP_DEPENDENCY_AUDIT:-0}" != "1" ]]; then
  pnpm audit --audit-level high
  uv export --quiet --project apps/api --all-extras --no-dev --no-emit-local --output-file "$migration_dir/api.txt"
  uvx pip-audit --requirement "$migration_dir/api.txt"
  uv export --quiet --project packages/music-engine --extra pdf --no-dev --no-emit-local --output-file "$migration_dir/music.txt"
  uvx pip-audit --requirement "$migration_dir/music.txt"
  uv export --quiet --project ml --no-dev --no-emit-local --output-file "$migration_dir/ml.txt"
  uvx pip-audit --requirement "$migration_dir/ml.txt"
fi
