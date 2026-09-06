FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

ARG UV_VERSION=0.12.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake git libopus-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY packages/music-engine /app/packages/music-engine
COPY ml /app/ml
COPY apps/api /app/apps/api
COPY scripts /app/scripts
COPY MODEL_LICENSING.md THIRD_PARTY_NOTICES.md /app/

RUN uv sync --project /app/apps/api --frozen --no-dev --no-editable --extra research

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /app /app
COPY infra/docker/worker-entrypoint.sh /usr/local/bin/drumscribe-worker-entrypoint

RUN chmod 0755 /usr/local/bin/drumscribe-worker-entrypoint \
    && useradd --create-home --uid 10001 drumscribe \
    && chown -R drumscribe:drumscribe /app /home/drumscribe

USER drumscribe
ENV HF_HOME=/home/drumscribe/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    TORCH_HOME=/home/drumscribe/.cache/torch

RUN HF_HUB_OFFLINE=0 python /app/scripts/prepare_production_model_cache.py \
    --repository /app \
    --cache-root /home/drumscribe/.cache

WORKDIR /app/apps/api
ENTRYPOINT ["drumscribe-worker-entrypoint"]
CMD ["celery", "-A", "drumscribe_api.tasks:celery_app", "worker", "--loglevel=INFO", "--concurrency=1"]
