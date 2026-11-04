#!/usr/bin/env sh
# Run the golden evals inside the API container (plan WP9.2).

set -eu

CONTAINER="${EVALS_CONTAINER:-charie-api-1}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "No container called $CONTAINER. Run 'make up' first." >&2
    exit 1
fi

if [ -z "${EVALS_ORG_ID:-}" ]; then
    echo "EVALS_ORG_ID is not set." >&2
    echo "It needs an organization with the pizza seed registered as a data" >&2
    echo "source — the same state 'make agent.smoke' needs." >&2
    exit 1
fi

docker exec "$CONTAINER" sh -c "exec mkdir -p /tmp/evals"
docker cp "$ROOT/ops/evals/runner.py" "$CONTAINER:/tmp/evals/runner.py" >/dev/null
docker cp "$ROOT/ops/evals/golden.yaml" "$CONTAINER:/tmp/evals/golden.yaml" >/dev/null
docker cp "$ROOT/ops/seed/truths.json" "$CONTAINER:/tmp/evals/truths.json" >/dev/null
docker cp "$ROOT/apps/api/tests/llm_fixture.py" "$CONTAINER:/tmp/evals/llm_fixture.py" >/dev/null

# `exec` first: Git Bash rewrites a leading `/` into a Windows path.
docker exec \
    -e EVALS_ORG_ID="$EVALS_ORG_ID" \
    -e EVALS_SOURCE="${EVALS_SOURCE:-Demo}" \
    -e EVALS_LIVE="${EVALS_LIVE:-}" \
    -e EVALS_TOKEN_BUDGET="${EVALS_TOKEN_BUDGET:-400000}" \
    "$CONTAINER" sh -c "exec python /tmp/evals/runner.py $*"
