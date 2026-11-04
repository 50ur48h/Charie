#!/usr/bin/env bash
# Run the API (internal) and the web app (public); stop the container if either exits.
set -uo pipefail

if [ "${CHARIE_BOOTSTRAP:-}" = "1" ]; then
  # The one-command demo: a secrets key kept on the data volume, then migrate and connect.
  key_file=/app/ops/.secrets/local_secrets_key
  if [ -z "${LOCAL_SECRETS_KEY:-}" ]; then
    if [ ! -s "$key_file" ]; then
      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" >"$key_file"
    fi
    LOCAL_SECRETS_KEY=$(cat "$key_file")
    export LOCAL_SECRETS_KEY
  fi
  python -m charie.ops.bootstrap || exit 1
fi

uvicorn charie.main:app --host 127.0.0.1 --port 8000 &
api=$!
node /app/web/server.js &
web=$!

trap 'kill -TERM "$api" "$web" 2>/dev/null' TERM INT
wait -n "$api" "$web"
status=$?
kill -TERM "$api" "$web" 2>/dev/null
wait
exit "$status"
