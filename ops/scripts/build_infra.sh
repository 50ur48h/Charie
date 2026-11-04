#!/usr/bin/env sh
# Compile every Bicep module and both parameter files.

set -eu

# Obvious dummies, and deliberately not plausible ones.
POSTGRES_ADMIN_PASSWORD=${POSTGRES_ADMIN_PASSWORD:-lint-only-not-a-password}
BUDGET_ALERT_EMAIL=${BUDGET_ALERT_EMAIL:-lint@example.invalid}
OIDC_AUTHORITY=${OIDC_AUTHORITY:-https://lint.invalid/lint-only/v2.0}
OIDC_AUDIENCE=${OIDC_AUDIENCE:-api://lint-only}
export POSTGRES_ADMIN_PASSWORD BUDGET_ALERT_EMAIL OIDC_AUTHORITY OIDC_AUDIENCE

echo "Compiling infra/main.bicep..."
az bicep build --file infra/main.bicep --stdout >/dev/null

for params in infra/params/*.bicepparam; do
  echo "Compiling $params..."
  az bicep build-params --file "$params" --stdout >/dev/null
done

echo "infra: every module and parameter file compiles."
