#!/bin/sh
# Apply ops/seed/seed_pizza_mssql.sql to the compose SQL Server (`make seed.mssql`).
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"

COMPOSE="docker compose --env-file .env -f ops/docker-compose.yml"

if ! $COMPOSE --profile mssql ps --status running --services 2>/dev/null | grep -qx mssql; then
	echo "The mssql container is not running. Start it with: make up.mssql" >&2
	exit 1
fi

# Read from .env rather than the environment: this script is run through make.
readonly_password=$(sed -n 's/^MSSQL_PIZZA_READONLY_PASSWORD=//p' .env | head -n 1)
if [ -z "$readonly_password" ]; then
	echo "MSSQL_PIZZA_READONLY_PASSWORD is not set in .env (see .env.example)." >&2
	exit 1
fi

printf 'Seeding the SQL Server pizza database...\n'

# Both passwords are expanded by the shell inside the container.
$COMPOSE exec -T -e RO_PASSWORD="$readonly_password" mssql \
	sh -c 'exec /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -C -b -v ReadonlyPassword="$RO_PASSWORD"' \
	<ops/seed/seed_pizza_mssql.sql

printf '\nRegister it as a data source with the pizza_readonly login, never with sa.\n'
