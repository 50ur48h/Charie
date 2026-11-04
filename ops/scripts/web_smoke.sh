#!/usr/bin/env sh
# The Phase 11 gate's smoke: a real stack, a real browser, a scripted model.

set -eu

if [ ! -f .env ]; then
  echo "No .env found. Run 'make env' first." >&2
  exit 1
fi

. "$(dirname "$0")/env_file.sh"

PROJECT=${SMOKE_PROJECT:-charie-smoke}

# Deliberately not one off the defaults. 3100 is the hermetic Playwright suite's and 5433 is the...
SMOKE_WEB_PORT=${SMOKE_WEB_PORT:-3200}
SMOKE_API_PORT=${SMOKE_API_PORT:-8200}
SMOKE_PG_PORT=${SMOKE_PG_PORT:-5532}
SMOKE_PIZZA_PORT=${SMOKE_PIZZA_PORT:-6643}

PLATFORM_DB_USER=$(env_value PLATFORM_DB_USER)
PLATFORM_DB_NAME=$(env_value PLATFORM_DB_NAME)
PLATFORM_DB_PASSWORD=$(env_value PLATFORM_DB_PASSWORD)
APP_DB_PASSWORD=$(env_value APP_DB_PASSWORD)
SEED_PIZZA_READONLY_PASSWORD=$(env_value SEED_PIZZA_READONLY_PASSWORD)
LOCAL_SECRETS_KEY=$(env_value LOCAL_SECRETS_KEY)

: "${PLATFORM_DB_USER:?PLATFORM_DB_USER missing from .env}"
: "${PLATFORM_DB_NAME:?PLATFORM_DB_NAME missing from .env}"
: "${PLATFORM_DB_PASSWORD:?PLATFORM_DB_PASSWORD missing from .env}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD missing from .env}"
: "${SEED_PIZZA_READONLY_PASSWORD:?SEED_PIZZA_READONLY_PASSWORD missing from .env}"

# The walk registers a database, so the API must be able to encrypt a credential.
if [ -z "$LOCAL_SECRETS_KEY" ]; then
  echo "No LOCAL_SECRETS_KEY in .env — minting one for this stack only."
  LOCAL_SECRETS_KEY=$(uv run --directory apps/api python -c \
    "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
fi

# --- What this stack is, overriding whatever .env says ---
export LOCAL_SECRETS_KEY
export SECRETS_BACKEND=local
export TLS_LOCAL_HOSTS=seed-pizza-pg

#: A stub in the ordinary image, selected by environment and refused at boot in production twice...
export LLM_PROVIDERS=scripted
export LLM_MODELS='{"scripted":{"small":"scripted-1","mid":"scripted-1","strong":"scripted-1"}}'
export LLM_ROLE_MAP='{}'
# One model, no prices, no cap.
export LLM_PRICES='{}'
export LLM_RUN_COST_LIMIT_USD=
export LLM_REFUSE_UNPRICED_WHEN_CAPPED=

# Nothing in this stack may reach a paid API, whatever is in .env.
export OPENAI_API_KEY=
export ANTHROPIC_API_KEY=
export EMBEDDINGS_PROVIDER=
export EMBEDDINGS_MODEL=

# Sign-in, pinned end to end. A developer's .env is quite likely to say `entra` — the owner's does.
export AUTH_MODE=dev
export NEXT_PUBLIC_AUTH_MODE=dev
export OIDC_AUTHORITY=
export OIDC_ISSUER=
export OIDC_AUDIENCE=charie-api

# `DEV_ISSUER_URL` is not a browser address, and this is the trap.
export DEV_ISSUER_URL="http://localhost:8000/dev"

# These two are the browser's view, and so do carry the published port.
export NEXT_PUBLIC_API_URL="http://localhost:${SMOKE_API_PORT}"
export CORS_ORIGINS="http://localhost:${SMOKE_WEB_PORT}"

export WEB_PORT=$SMOKE_WEB_PORT
export API_PORT=$SMOKE_API_PORT
export PLATFORM_DB_PORT=$SMOKE_PG_PORT
export SEED_PIZZA_PORT=$SMOKE_PIZZA_PORT

# The smoke overlay replaces the two host bind mounts with named volumes.
COMPOSE="docker compose --profile test-fixtures -p $PROJECT --env-file .env -f ops/docker-compose.yml -f ops/docker-compose.smoke.yml"

teardown() {
  if [ "${SMOKE_KEEP:-}" = "1" ]; then
    echo
    echo "Stack left up as $PROJECT: web http://localhost:${SMOKE_WEB_PORT}"
    # `--env-file .env` is not optional in that command.
    echo "Take it down with:"
    echo "  docker compose --profile test-fixtures -p $PROJECT --env-file .env -f ops/docker-compose.yml -f ops/docker-compose.smoke.yml down --volumes"
    return
  fi
  echo
  echo "Taking $PROJECT down..."
  # Volumes too: this database exists only for one walk.
  $COMPOSE down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap teardown EXIT INT TERM

if [ "${SMOKE_REUSE:-}" != "1" ]; then
  echo "Starting $PROJECT (model: scripted)..."
  # `--wait` rather than a sleep: every service in the file has a healthcheck.
  $COMPOSE up -d --build --wait

  echo "Applying migrations..."
  DATABASE_URL="postgresql+asyncpg://${PLATFORM_DB_USER}:${PLATFORM_DB_PASSWORD}@localhost:${SMOKE_PG_PORT}/${PLATFORM_DB_NAME}" \
    uv run --directory apps/api alembic upgrade head

  echo "Granting charie_app its login..."
  $COMPOSE exec -T platform-pg \
    psql -v ON_ERROR_STOP=1 \
    -U "$PLATFORM_DB_USER" \
    -d "$PLATFORM_DB_NAME" \
    -v app_password="$APP_DB_PASSWORD" \
    <ops/sql/app_role.sql >/dev/null

  echo "Seeding the pizza fixture..."
  uv run ops/seed/seed_pizza.py
fi

echo
echo "Driving http://localhost:${SMOKE_WEB_PORT} in Chromium..."

# `seed-pizza-pg` is how the API reaches the database.
if SMOKE_BASE_URL="http://localhost:${SMOKE_WEB_PORT}" \
  SMOKE_DB_HOST=seed-pizza-pg \
  SMOKE_DB_PORT=5432 \
  SMOKE_DB_PASSWORD="$SEED_PIZZA_READONLY_PASSWORD" \
  pnpm --dir apps/web exec playwright test --config playwright.compose.config.ts "$@"; then
  exit 0
fi

# Say what the containers saw, here rather than in the caller.
echo
echo "--- api, last 100 lines -------------------------------------------------"
$COMPOSE logs --tail 100 api || true
echo "--- web, last 50 lines --------------------------------------------------"
$COMPOSE logs --tail 50 web || true
exit 1
