#!/usr/bin/env bash
# The API's real coverage number, assembled from every job that measured part of it (B-016).

set -euo pipefail

API_DIR=${API_DIR:-apps/api}
COVERAGE_DATA_DIR=${COVERAGE_DATA_DIR:-$API_DIR/coverage-data}
COVERAGE_FAIL_UNDER=${COVERAGE_FAIL_UNDER:-70}

# The shards that exist, and what each one is the only source of.
shard_note() {
  case $1 in
    api) printf 'the API suite, against Postgres' ;;
    mssql) printf 'the connector suite, against SQL Server' ;;
    *) printf 'unrecognised shard' ;;
  esac
}

shopt -s nullglob
shards=("$COVERAGE_DATA_DIR"/.coverage.*)
shopt -u nullglob

if ((${#shards[@]} == 0)); then
  # Every job that would have produced a shard was skipped by the path filters.
  echo "coverage: no shards were uploaded — nothing ran that measures anything."
  exit 0
fi

echo "coverage: combining ${#shards[@]} shard(s):"
found_mssql=0
for shard in "${shards[@]}"; do
  name=${shard##*/.coverage.}
  printf '  %-8s %s\n' "$name" "$(shard_note "$name")"
  [[ $name == mssql ]] && found_mssql=1
done

if ((found_mssql == 0)); then
  echo
  echo "coverage: no SQL Server shard in this run, so connectors/sqlserver.py is"
  echo "          measured only by what the API suite imports. The total below is"
  echo "          structurally low for that reason, not because code lost tests."
fi

echo
# `combine` consumes the shard files and leaves one `.coverage` behind.
data_dir=$(cd "$COVERAGE_DATA_DIR" && pwd)
uv run --directory "$API_DIR" coverage combine "$data_dir"
uv run --directory "$API_DIR" coverage report --fail-under="$COVERAGE_FAIL_UNDER"
