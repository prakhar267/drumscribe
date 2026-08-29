FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete
RUN pip install --no-cache-dir uv==0.12.0
COPY packages/music-engine ./packages/music-engine
COPY apps/api ./apps/api
WORKDIR /app/apps/api
RUN uv sync --no-dev --frozen

RUN useradd --create-home --uid 10001 drumscribe
USER drumscribe
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "drumscribe_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
