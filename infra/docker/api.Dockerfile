FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir uv

COPY packages/music-engine /app/packages/music-engine
COPY apps/api /app/apps/api
RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python /app/packages/music-engine /app/apps/api

COPY MODEL_LICENSING.md /app/MODEL_LICENSING.md
WORKDIR /app/apps/api

RUN useradd --create-home --uid 10001 drumscribe \
    && chown -R drumscribe:drumscribe /app
USER drumscribe

EXPOSE 8000
CMD ["uvicorn", "drumscribe_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

