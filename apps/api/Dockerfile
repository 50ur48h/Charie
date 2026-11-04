# syntax=docker/dockerfile:1
# Targets: dev (uvicorn --reload, for compose) and prod (runtime only, non-root).

# --- Base — uv's official image, which is python:3.12-slim-bookworm plus uv ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# --- Dependency layers — cached on the lockfile alone, so editing source code ---
FROM base AS deps-runtime
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

FROM base AS deps-dev
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# --- dev — hot reload ---
FROM base AS dev

ARG GIT_SHA=unknown
ENV BUILD_ENV=dev \
    GIT_SHA=${GIT_SHA}

# Before the dependency layer, so editing a script or a source file does not reinstall a driver...
COPY docker/install-odbc.sh /tmp/install-odbc.sh
RUN sh /tmp/install-odbc.sh && rm /tmp/install-odbc.sh

COPY --from=deps-dev /app/.venv /app/.venv
COPY pyproject.toml uv.lock README.md ./
# alembic.ini as in prod, so a dev image deployed on its own can run `alembic upgrade head`.
COPY alembic.ini ./alembic.ini
COPY src ./src
COPY tests ./tests
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked

# The image declares the two directories it writes to (WP11.2b).
RUN mkdir -p /app/ops/.secrets /app/ops/artifacts \
    && groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "charie.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- Builder for prod — installs the project itself against runtime deps only ---
FROM base AS build
COPY --from=deps-runtime /app/.venv /app/.venv
COPY pyproject.toml uv.lock README.md ./
# alembic.ini travels with the image (WP12.2).
COPY alembic.ini ./alembic.ini
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

# --- prod — runtime only ---
FROM python:3.12-slim-bookworm AS prod

ARG GIT_SHA=unknown
ENV BUILD_ENV=prod \
    GIT_SHA=${GIT_SHA} \
    ENV=prod \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home app

# The same driver install as the dev target, from the same script.
COPY docker/install-odbc.sh /tmp/install-odbc.sh
RUN sh /tmp/install-odbc.sh && rm /tmp/install-odbc.sh

WORKDIR /app
COPY --from=build --chown=app:app /app/.venv /app/.venv
COPY --from=build --chown=app:app /app/src /app/src
COPY --from=build --chown=app:app /app/alembic.ini /app/alembic.ini

# The development token issuer is physically absent from this image.
RUN rm -f /app/src/charie/auth/dev_issuer.py \
    && test ! -f /app/src/charie/auth/dev_issuer.py

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]

CMD ["uvicorn", "charie.main:app", "--host", "0.0.0.0", "--port", "8000"]
