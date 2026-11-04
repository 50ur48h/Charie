#!/usr/bin/env sh
# Read one value out of .env, without sourcing it (B-102).

# Last assignment wins, as a shell would.
env_value() {
  value=$(sed -n "s/^$1=//p" "${ENV_FILE:-.env}" | tail -n 1)
  case $value in
  \"*\") value=${value#\"}; value=${value%\"} ;;
  \'*\') value=${value#\'}; value=${value%\'} ;;
  esac
  printf '%s' "$value"
}
