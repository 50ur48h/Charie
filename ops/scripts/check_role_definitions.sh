#!/usr/bin/env sh
# Every role definition id in `roles.bicep` names a role that exists (B-130).

set -eu

ROLES_FILE="${ROLES_FILE:-infra/modules/roles.bicep}"
GITLEAKS_FILE="${GITLEAKS_FILE:-.gitleaks.toml}"

ALLOWLIST_ONLY=0
[ "${1:-}" = "--allowlist-only" ] && ALLOWLIST_ONLY=1

[ -f "$ROLES_FILE" ] || {
  echo "check_role_definitions: $ROLES_FILE does not exist — is the path right?" >&2
  exit 1
}

# Quoted GUID literals, deduplicated.
ids=$(grep -oE "'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'" "$ROLES_FILE" |
  tr -d "'" | sort -u)

if [ -z "$ids" ]; then
  # Not "nothing to check": a file that yields no ids means the extraction has stopped matching...
  echo "check_role_definitions: found no role definition ids in $ROLES_FILE." >&2
  echo "Either the file no longer assigns roles, or this pattern has stopped" >&2
  echo "matching it. Both need a person." >&2
  exit 1
fi

failures=0

# --- The allowlist, in both directions.
if [ -f "$GITLEAKS_FILE" ]; then
  allowed=$(grep -oE "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}" "$GITLEAKS_FILE" |
    sort -u)

  for id in $ids; do
    if ! printf '%s\n' "$allowed" | grep -qx "$id"; then
      printf '  FAIL  %s is used by %s and not allowlisted in %s\n' \
        "$id" "$ROLES_FILE" "$GITLEAKS_FILE" >&2
      echo "        gitleaks reads a public role id as a generic-api-key, so the" >&2
      echo "        scanner fails on it. Add it beside the others, with the role" >&2
      echo "        name in the comment." >&2
      failures=$((failures + 1))
    fi
  done

  for id in $allowed; do
    if ! printf '%s\n' "$ids" | grep -qx "$id"; then
      printf '  FAIL  %s is allowlisted in %s and no longer used by %s\n' \
        "$id" "$GITLEAKS_FILE" "$ROLES_FILE" >&2
      echo "        A stale exemption is one a real secret could inherit. Remove it." >&2
      failures=$((failures + 1))
    fi
  done

  [ "$failures" -gt 0 ] || echo "  ok    every role id is allowlisted, and nothing stale is"
fi

if [ "$ALLOWLIST_ONLY" -eq 1 ]; then
  if [ "$failures" -gt 0 ]; then
    echo "check_role_definitions: $failures allowlist problem(s)." >&2
    exit 1
  fi
  echo "check_role_definitions: $ROLES_FILE and $GITLEAKS_FILE agree."
  exit 0
fi

# --- Does each id name a role that exists? Only Azure knows. ----------------
for id in $ids; do
  name=$(az role definition list --query "[?name=='$id'].roleName" -o tsv --only-show-errors 2>/dev/null | head -1)
  if [ -n "$name" ]; then
    printf '  ok    %s  %s\n' "$id" "$name"
  else
    printf '  FAIL  %s  no such role definition in this subscription\n' "$id" >&2
    failures=$((failures + 1))
  fi
done

if [ "$failures" -gt 0 ]; then
  echo >&2
  echo "check_role_definitions: $failures id(s) name no role that exists." >&2
  echo "Look the role up rather than recalling it:" >&2
  echo "  az role definition list --name 'Key Vault Secrets Officer' --query '[].name' -o tsv" >&2
  echo "Deploying with one of these fails partway through with" >&2
  echo "RoleDefinitionDoesNotExist, after the resource group has been touched." >&2
  exit 1
fi

echo "check_role_definitions: every role id in $ROLES_FILE names a real role."
