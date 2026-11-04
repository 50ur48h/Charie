#!/usr/bin/env sh
# Load a file of metric definitions into a registered data source.

set -eu

CONTAINER="${DEMO_CONTAINER:-charie-api-1}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FILE="${FILE:?Set FILE to a definitions JSON file: make seed.definitions FILE=... SOURCE=...}"

if [ ! -f "$ROOT/$FILE" ] && [ ! -f "$FILE" ]; then
  echo "No such file: $FILE" >&2
  exit 1
fi
[ -f "$FILE" ] || FILE="$ROOT/$FILE"

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "No container called $CONTAINER. Run 'make up' first." >&2
  exit 1
fi

docker cp "$ROOT/ops/seed/provision_definitions.py" "$CONTAINER:/tmp/provision_definitions.py" >/dev/null
docker cp "$FILE" "$CONTAINER:/tmp/definitions.json" >/dev/null

# Both halves of the Git Bash path rewrite, and they bite differently.
MSYS_NO_PATHCONV=1 docker exec \
  -e DEFINITIONS_FILE=/tmp/definitions.json \
  -e DEFINITIONS_SOURCE="${SOURCE:-}" \
  -e DEMO_ORG_NAME="${DEMO_ORG_NAME:-Demo}" \
  "$CONTAINER" sh -c "exec python /tmp/provision_definitions.py"
