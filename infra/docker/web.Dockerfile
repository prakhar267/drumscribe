FROM node:22-bookworm-slim AS build
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable
WORKDIR /app

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --filter @drumscribe/web... --frozen-lockfile=false

COPY apps/web ./apps/web
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN pnpm --filter @drumscribe/web build

FROM node:22-bookworm-slim AS runtime
ENV NODE_ENV=production \
    PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH
RUN corepack enable \
    && useradd --create-home --uid 10001 drumscribe
WORKDIR /app
COPY --from=build --chown=drumscribe:drumscribe /app /app
USER drumscribe
EXPOSE 3000
CMD ["pnpm", "--filter", "@drumscribe/web", "start"]

