#!/usr/bin/env bash
# Start Charie: its own Postgres unless DATABASE_URL is given, then the API (internal) and web app.
set -uo pipefail

# Data lives in /app/ops (mount a volume there to keep it); a read-only mount falls back to /tmp.
ops=/app/ops
if ! mkdir -p "$ops/.secrets" 2>/dev/null || [ ! -w "$ops/.secrets" ]; then
  ops=/tmp/charie
  echo "start: /app/ops is not writable, so data lasts only until the container stops" >&2
  mkdir -p "$ops/.secrets"
fi
export LOCAL_SECRETS_PATH="${LOCAL_SECRETS_PATH:-$ops/.secrets/secrets.json}"
export ARTIFACTS_PATH="${ARTIFACTS_PATH:-$ops/artifacts}"
mkdir -p "$ARTIFACTS_PATH"

# A value generated once and kept beside the data, unless the environment already sets it.
kept() {
  local file="$ops/.secrets/$1"
  [ -s "$file" ] || python -c "$2" >"$file"
  cat "$file"
}
token='import secrets; print(secrets.token_urlsafe(24))'
fernet='from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
if [ -z "${LOCAL_SECRETS_KEY:-}" ]; then LOCAL_SECRETS_KEY=$(kept local_secrets_key "$fernet"); fi
if [ -z "${APP_DB_PASSWORD:-}" ]; then APP_DB_PASSWORD=$(kept app_db_password "$token"); fi
export LOCAL_SECRETS_KEY APP_DB_PASSWORD

stop_postgres() { :; }
if [ -z "${DATABASE_URL:-}" ]; then
  pgdata="$ops/pgdata"
  owner_password=$(kept postgres_password "$token")
  if [ ! -s "$pgdata/PG_VERSION" ]; then
    pwfile=$(mktemp)
    printf '%s\n' "$owner_password" >"$pwfile"
    initdb -D "$pgdata" -U charie --pwfile="$pwfile" -E UTF8 \
      --auth-local=trust --auth-host=scram-sha-256 >/dev/null || exit 1
    rm -f "$pwfile"
  fi
  pg_ctl -D "$pgdata" -l "$ops/postgres.log" -w \
    -o "-c listen_addresses=127.0.0.1 -c port=5432 -c jit=off -k /tmp" start >/dev/null || {
    cat "$ops/postgres.log" >&2
    exit 1
  }
  stop_postgres() { pg_ctl -D "$pgdata" -m fast stop >/dev/null 2>&1; }
  if ! psql -h /tmp -U charie -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'charie'" | grep -q 1; then
    createdb -h /tmp -U charie charie || exit 1
  fi
  export DATABASE_URL="postgresql://charie:${owner_password}@127.0.0.1:5432/charie"
fi

# The driver both URLs need, and the unprivileged login the API connects as.
eval "$(python -m charie.ops.urls)" || { stop_postgres; exit 1; }

if [ "${CHARIE_BOOTSTRAP:-}" = "1" ]; then
  python -m charie.ops.bootstrap prepare || { stop_postgres; exit 1; }
fi

uvicorn charie.main:app --host 127.0.0.1 --port 8000 &
api=$!
node /app/web/server.js &
web=$!

if [ "${CHARIE_BOOTSTRAP:-}" = "1" ]; then
  # Reading the demo database takes a few minutes; the app is already serving meanwhile.
  python -m charie.ops.bootstrap demo &
fi

trap 'kill -TERM "$api" "$web" 2>/dev/null' TERM INT
wait -n "$api" "$web"
status=$?
kill -TERM "$api" "$web" 2>/dev/null
wait "$api" "$web" 2>/dev/null
stop_postgres
exit "$status"
