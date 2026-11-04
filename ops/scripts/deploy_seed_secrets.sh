#!/usr/bin/env sh
# Put the three secrets the deployment needs into the vault (WP12.2).

set -eu

: "${KEY_VAULT:?KEY_VAULT is not set; it comes from the infra deployment outputs}"

# Set a secret only if it has no value yet.
seed_if_absent() {
  name=$1
  value=$2
  why=$3
  existing=$(az keyvault secret show --vault-name "$KEY_VAULT" --name "$name" \
    --query id -o tsv 2>/dev/null || true)
  if [ -n "$existing" ]; then
    echo "  $name: already set, left alone"
    return 0
  fi
  if [ -z "$value" ]; then
    echo "  $name: MISSING — $why" >&2
    return 1
  fi
  # `--value` is passed as an argument, so it would appear in a process listing on this runner.
  az keyvault secret set --vault-name "$KEY_VAULT" --name "$name" \
    --value "$value" --output none
  echo "  $name: written"
}

echo "Seeding $KEY_VAULT (values are never printed)"

failures=0

seed_if_absent openai-api-key "${OPENAI_API_KEY:-}" \
  "set the OPENAI_API_KEY repository secret; the agent cannot answer without a model" ||
  failures=$((failures + 1))

seed_if_absent database-password "${POSTGRES_ADMIN_PASSWORD:-}" \
  "the dev environment secret POSTGRES_ADMIN_PASSWORD is what the server was created with" ||
  failures=$((failures + 1))

# Generated, never chosen, and only on the first deploy. 32 bytes of urandom rendered as hex.
if ! az keyvault secret show --vault-name "$KEY_VAULT" --name app-database-password \
  --query id -o tsv >/dev/null 2>&1; then
  generated=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  [ -n "$generated" ] || {
    echo "  app-database-password: could not generate a password" >&2
    exit 1
  }
  seed_if_absent app-database-password "$generated" "generated here" ||
    failures=$((failures + 1))
  unset generated
else
  echo "  app-database-password: already set, left alone"
fi

if [ "$failures" -gt 0 ]; then
  echo "$failures secret(s) could not be seeded; the apps would not start." >&2
  exit 1
fi

echo "Vault seeded. Names only:"
az keyvault secret list --vault-name "$KEY_VAULT" --query "[].name" -o tsv | sed 's/^/  /'
