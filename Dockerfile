# syntax=docker/dockerfile:1
# Charie in one image: the web app on $PORT, proxying /api to the API on 127.0.0.1:8000.

# --- Web: dependencies, then the standalone build ---
FROM node:22-bookworm-slim AS web-base
ENV PNPM_HOME=/pnpm \
    PATH="/pnpm:${PATH}" \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /web

FROM web-base AS web-deps
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

FROM web-base AS web-build
# Same origin: the browser calls /api, and Next forwards it to the API in this container.
ENV NEXT_PUBLIC_API_URL=/api \
    NEXT_PUBLIC_AUTH_MODE=dev \
    NEXT_PUBLIC_ENV=local \
    NEXT_PUBLIC_DEV_SUBJECT=demo \
    CHARIE_INTERNAL_API_URL=http://127.0.0.1:8000
COPY --from=web-deps /web/node_modules ./node_modules
COPY apps/web/ ./
RUN pnpm build

# --- API: runtime dependencies, then the project ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS api-build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=apps/api/uv.lock,target=uv.lock \
    --mount=type=bind,source=apps/api/pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md apps/api/alembic.ini ./
COPY apps/api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

# --- Final image ---
FROM python:3.12-slim-bookworm

ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA} \
    BUILD_ENV=dev \
    ENV=dev \
    AUTH_MODE=dev \
    DEV_ISSUER_URL=http://127.0.0.1:8000/dev \
    LOCAL_SECRETS_PATH=/app/ops/.secrets/secrets.json \
    ARTIFACTS_PATH=/app/ops/artifacts \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

# The SQL Server driver, for customers on SQL Server.
COPY apps/api/docker/install-odbc.sh /tmp/install-odbc.sh
RUN sh /tmp/install-odbc.sh && rm /tmp/install-odbc.sh

COPY --from=web-base /usr/local/bin/node /usr/local/bin/node
RUN node --version \
    && groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home app

WORKDIR /app
COPY --from=api-build --chown=app:app /app/.venv /app/.venv
COPY --from=api-build --chown=app:app /app/src /app/src
COPY --from=api-build --chown=app:app /app/alembic.ini /app/alembic.ini
COPY --from=web-build --chown=app:app /web/.next/standalone /app/web
COPY --from=web-build --chown=app:app /web/.next/static /app/web/.next/static
COPY --chmod=755 ops/docker/start.sh /app/start.sh
RUN mkdir -p /app/ops/.secrets /app/ops/artifacts && chown -R app:app /app/ops

USER app
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

CMD ["/app/start.sh"]
