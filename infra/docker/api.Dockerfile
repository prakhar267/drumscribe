FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

ARG UV_VERSION=0.12.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY packages/music-engine /app/packages/music-engine
COPY apps/api /app/apps/api
RUN uv sync --project /app/apps/api --frozen --no-dev --no-editable

COPY MODEL_LICENSING.md /app/MODEL_LICENSING.md
WORKDIR /app/apps/api

RUN useradd --create-home --uid 10001 drumscribe \
    && chown -R drumscribe:drumscribe /app
USER drumscribe

EXPOSE 8000
CMD ["uvicorn", "drumscribe_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
