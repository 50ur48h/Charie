#!/usr/bin/env sh
# Build an organization the product can query, from an empty platform database (B-115).

set -eu

CONTAINER="${DEMO_CONTAINER:-charie-api-1}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if [ ! -f .env ]; then
  echo "No .env found. Run 'make env' first." >&2
  exit 1
fi

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "No container called $CONTAINER. Run 'make up' first." >&2
  exit 1
fi

# Read the value; do not source the file (B-102).
. "$(dirname "$0")/env_file.sh"

SEED_PIZZA_READONLY_PASSWORD=$(env_value SEED_PIZZA_READONLY_PASSWORD)

: "${SEED_PIZZA_READONLY_PASSWORD:?SEED_PIZZA_READONLY_PASSWORD missing from .env}"

docker cp "$ROOT/ops/seed/provision_demo.py" "$CONTAINER:/tmp/provision_demo.py" >/dev/null

# `exec` first: Git Bash rewrites a leading `/` into a Windows path.
docker exec \
  -e SEED_PIZZA_READONLY_PASSWORD="$SEED_PIZZA_READONLY_PASSWORD" \
  -e DEMO_ORG_NAME="${DEMO_ORG_NAME:-Demo}" \
  "$CONTAINER" sh -c "exec python /tmp/provision_demo.py"
