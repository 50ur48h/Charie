#!/usr/bin/env bash
# Run the API (internal) and the web app (public); stop the container if either exits.
set -uo pipefail

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
