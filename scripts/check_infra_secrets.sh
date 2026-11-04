#!/usr/bin/env bash
# No secret value may be written into a deployment template.

set -euo pipefail

INFRA_DIR=${INFRA_DIR:-infra}

# A quoted literal assigned to something whose name says secret, or a quoted email address.
readonly SECRET_ASSIGNMENT="=[[:space:]]*'[^']*'"
readonly SECRET_NAMES='(password|passwd|secret|apikey|api_key|connectionstring|accountkey|sas|token)'

# Hostnames that are part of Azure's own namespace rather than somebody's inbox.
readonly ALLOWED='(example\.invalid|azurecr\.io|database\.azure\.com|blob\.core\.windows\.net|vaultcore\.azure\.net|aka\.ms)'

# A GUID is not a secret, and one of them is unavoidable here.
readonly GUID="'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'\$"


scan() {
  local dir=$1 found=0

  # A quoted value assigned to a secret-shaped name, excluding bare GUIDs.
  if grep -rniE "${SECRET_NAMES}[a-z_]*[[:space:]]*${SECRET_ASSIGNMENT}" "$dir" \
    --include='*.bicep' --include='*.bicepparam' 2>/dev/null |
    grep -viE "$GUID"; then
    found=1
  fi

  # A quoted email address, which is only ever a person.
  if grep -rniE "'[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}'" "$dir" \
    --include='*.bicep' --include='*.bicepparam' 2>/dev/null |
    grep -viE "$ALLOWED"; then
    found=1
  fi

  return $found
}

selftest() {
  local passed=0 failed=0
  # Global, not local. The EXIT trap runs after this function has returned.
  dir=$(mktemp -d)
  trap 'rm -rf "$dir"' EXIT

  # The correct patterns, which must pass.
  cat >"$dir/good.bicepparam" <<'GOOD'
using '../main.bicep'
param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD')
param budgetAlertEmail = readEnvironmentVariable('BUDGET_ALERT_EMAIL')
param postgresAdminLogin = 'charie_admin'
param registryHost = 'crchariedev01.azurecr.io'
GOOD

  # A role definition id: a name containing "secret", holding a public constant.
  cat >"$dir/roles.bicep" <<'ROLES'
var keyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
ROLES

  if INFRA_DIR=$dir scan "$dir" >/dev/null 2>&1; then
    printf '  ok    the correct patterns pass, role GUIDs included\n'
    passed=$((passed + 1))
  else
    printf '  FAIL  the correct patterns were flagged\n' >&2
    failed=$((failed + 1))
  fi

  # Each of these must be caught. A guard that cannot fail is decoration.
  local case
  for case in \
    "param adminPassword = 'hunter2'" \
    "param apiKey = 'placeholder-not-a-real-key'" \
    "var connectionString = 'AccountKey=abc123'" \
    "param alertEmail = 'someone@gmail.com'"; do
    printf '%s\n' "$case" >"$dir/bad.bicep"
    if INFRA_DIR=$dir scan "$dir" >/dev/null 2>&1; then
      printf '  FAIL  not caught: %s\n' "$case" >&2
      failed=$((failed + 1))
    else
      printf '  ok    caught: %s\n' "$case"
      passed=$((passed + 1))
    fi
    rm -f "$dir/bad.bicep"
  done

  printf 'check_infra_secrets --selftest: %d passed, %d failed\n' "$passed" "$failed"
  ((failed == 0))
}

if [[ ${1:-} == --selftest ]]; then
  selftest
  exit $?
fi

if [[ ! -d $INFRA_DIR ]]; then
  printf 'check_infra_secrets: no %s directory; nothing to check\n' "$INFRA_DIR"
  exit 0
fi

if scan "$INFRA_DIR"; then
  printf 'check_infra_secrets: no secret value in %s\n' "$INFRA_DIR"
  exit 0
fi

cat >&2 <<'WHY'

A quoted literal in infra/ looks like a credential or a personal address.

Secrets are not written into templates. Key Vault is created empty and filled out
of band; apps reference secrets by URI and read them with a managed identity; a
parameter that would carry one is read from the environment at deploy time:

    param postgresAdminPassword = readEnvironmentVariable('POSTGRES_ADMIN_PASSWORD')

See infra/README.md.
WHY
exit 1
