#!/usr/bin/env bash
# The environment a developer has is not the environment the product runs in.

set -euo pipefail

ENV_EXAMPLE_FILE=${ENV_EXAMPLE_FILE:-.env.example}
COMPOSE_FILE=${COMPOSE_FILE:-ops/docker-compose.yml}
SETTINGS_FILE=${SETTINGS_FILE:-apps/api/src/charie/config.py}
INFRA_DIR=${INFRA_DIR:-infra/modules}

# --- The declaration ---
# `KEY | why it is not passed to any service`.
readonly HOST_ONLY='
DATABASE_URL | The owner connection, rebuilt inside compose: the database is `platform-pg` on the compose network, not `localhost:5432`. Used on the host by alembic and psql.
APP_DATABASE_URL | The same, for the unprivileged application role the API actually connects as.
ENV | Compose sets `ENV: local` literally, because a stack of containers on somebody laptop *is* local. Passing the host value would let a stray `ENV=prod` in a .env disable dev-only features in a local stack.
ARTIFACTS_PATH | The container writes to `/app/ops/ops/artifacts` only because a bind mount puts the host directory there. Passing a host path would move the setting and not the mount, and query results would land somewhere nothing is watching.
LOCAL_SECRETS_PATH | Same shape: compose points the API at `/app/ops/.secrets/secrets.json`, which is the host file through a mount. The host value is a host path.
SEED_PIZZA_HOST | `localhost` for tools run on the host. Inside the network the database is `seed-pizza-pg`, which the seed service already knows.
SEED_PIZZA_READONLY_USER | The read-only login `make seed` creates and a person types into the data-source form. No container reads it; the API receives it through the API, encrypted, like any customer credential.
SEED_PIZZA_READONLY_PASSWORD | As above.
MSSQL_DB | Read by `ops/scripts/seed_mssql.sh`, which runs on the host against the on-demand SQL Server container.
MSSQL_PIZZA_READONLY_USER | Created by that seed script and typed into the data-source form, exactly like the Postgres read-only login.
MSSQL_PIZZA_READONLY_PASSWORD | As above.
DB_PASSWORD | Deployment-only (WP12.2). Locally the owner password is inside DATABASE_URL and nothing needs it separately; in Azure the template builds the DSN in the clear and takes only this from Key Vault, and only the migration job is given it. Passing it to a compose service would add a second source of truth for a password that is already in the URL beside it.
'

# Keys the image or the build sets.
readonly PLATFORM_ENV='
AZURE_CLIENT_ID | Read by `DefaultAzureCredential` to pick the user-assigned managed identity, not by `Settings`. Without it a container with more than one identity cannot tell which to present.
APPLICATIONINSIGHTS_CONNECTION_STRING | Read by the OpenTelemetry exporter (WP12.3), not by this application. Set here so the wiring exists before the code that uses it.
'

readonly SET_BY_THE_BUILD='
GIT_SHA | Baked in at `docker build` time by the Makefile so `/healthz` can say which commit is running. A value in a .env would be a claim about an image it did not build.
BUILD_ENV | Set by the Dockerfile target that built the process, and the reason the prod image can physically exclude the dev token issuer. A person setting it would be asserting something about an image rather than configuring one.
'

failures=0

fail() {
  printf 'check_env: %s\n' "$1" >&2
  failures=$((failures + 1))
}

# --- Reading the three files ------------------------------------------------

# Every key `.env.example` documents, commented ones included.
documented_keys() {
  sed -E 's/\r$//; s/^[[:space:]]*#[[:space:]]*//' "$ENV_EXAMPLE_FILE" |
    { grep -oE '^[A-Z_][A-Z0-9_]*=' || true; } | tr -d '=' | sort -u
}

# Every `${KEY}` compose expands, with comment lines stripped first.
compose_keys() {
  sed -E 's/\r$//; s/^[[:space:]]*#.*$//' "$COMPOSE_FILE" |
    { grep -oE '\$\{[A-Z_][A-Z0-9_]*' || true; } | sed 's/^\${//' | sort -u
}

# Every field of `Settings`, as the environment variable name pydantic reads it for.
settings_keys() {
  awk '
    /^class Settings\(BaseSettings\):/ { inside = 1; next }
    inside && /^(class |def |@)/ { inside = 0 }
    inside && /^    [a-z_][a-z0-9_]*[[:space:]]*:/ {
      sub(/\r$/, "")
      name = $1
      sub(/:.*/, "", name)
      if (name != "model_config") print toupper(name)
    }
  ' "$SETTINGS_FILE" | sort -u
}

# `KEY | reason` lines out of a declaration block.
declared_keys() {
  printf '%s\n' "$1" | { grep -E '^[A-Z_][A-Z0-9_]*[[:space:]]*\|' || true; } |
    sed -E 's/^([A-Z_][A-Z0-9_]*)[[:space:]]*\|.*$/\1/' | sort -u
}

declared_reason() {
  printf '%s\n' "$2" | { grep -E "^$1[[:space:]]*\|" || true; } |
    sed -E 's/^[A-Z_][A-Z0-9_]*[[:space:]]*\|[[:space:]]*//'
}

contains() {
  printf '%s\n' "$2" | grep -qxF "$1"
}

# Every environment variable the deployment templates set on a container.
infra_env_keys() {
  local files
  # `set -e` plus `pipefail` makes this delicate.
  files=$(find "$INFRA_DIR" -maxdepth 1 -name '*.bicep' 2>/dev/null || true)
  [[ -n $files ]] || return 0
  # shellcheck disable=SC2086
  cat $files 2>/dev/null | tr -d '\015' |
    { grep -vE '^[[:space:]]*//' || true; } |
    { grep -oE "name: '[A-Z_][A-Z0-9_]*'" || true; } |
    sed -E "s/name: '//; s/'$//" | sort -u
  return 0
}

# What a template actually assigns to a key.
infra_value_for() {
  local key=$1 files
  files=$(find "$INFRA_DIR" -maxdepth 1 -name '*.bicep' 2>/dev/null || true)
  [[ -n $files ]] || return 0
  # shellcheck disable=SC2086
  cat $files 2>/dev/null | tr -d '\015' |
    { grep -vE '^[[:space:]]*//' || true; } |
    { grep -A2 -E "name: '$key'" || true; } |
    { grep -oE "value: '[^']*'" || true; } |
    sed -E "s/value: '//; s/'$//" | head -n 1
  return 0
}

# --- 1. A documented key is passed, or it is declared -----------------------

check_every_documented_key_reaches_a_service() {
  local documented=$1 compose=$2 host_only=$3 build=$4
  local key
  while read -r key; do
    [[ -n $key ]] || continue
    contains "$key" "$compose" && continue
    contains "$key" "$host_only" && continue
    contains "$key" "$build" && continue
    fail "$key is documented in $ENV_EXAMPLE_FILE and passed to no service in $COMPOSE_FILE.
    Either add it to the service that reads it, or declare it in HOST_ONLY with
    the reason it stays on the host. This is B-086: EMBEDDINGS_* was set on every
    developer's machine and reached nothing in the container, for a whole phase."
  done <<<"$documented"
}

# --- 2. A declaration names a key that exists -------------------------------

check_declarations_are_not_stale() {
  local documented=$1 host_only=$2
  local key
  while read -r key; do
    [[ -n $key ]] || continue
    contains "$key" "$documented" ||
      fail "$key is declared HOST_ONLY but $ENV_EXAMPLE_FILE does not document it.
    Either the key was removed and the declaration should go with it, or it was
    renamed and the declaration now excuses a key nobody has."
  done <<<"$host_only"
}

# --- 3. A declaration is not contradicted by the file it describes ----------

check_declarations_are_not_contradicted() {
  local compose=$1 host_only=$2
  local key
  while read -r key; do
    [[ -n $key ]] || continue
    if contains "$key" "$compose"; then
      fail "$key is declared HOST_ONLY and $COMPOSE_FILE passes it anyway.
    The declaration says nobody meant this to reach a container. Delete the
    declaration if passing it was right; remove it from compose if it was not."
    fi
  done <<<"$host_only"
}

# --- 4. Nothing is passed that nobody documented ----------------------------

check_every_passed_key_is_documented() {
  local documented=$1 compose=$2 build=$3
  local key
  while read -r key; do
    [[ -n $key ]] || continue
    contains "$key" "$documented" && continue
    contains "$key" "$build" && continue
    fail "$COMPOSE_FILE expands \${$key} and $ENV_EXAMPLE_FILE never mentions it.
    Somebody setting this project up from the example file cannot discover it,
    and will get whatever the compose default happens to be."
  done <<<"$compose"
}

# --- 5. Every setting the API reads has a line somebody can find ------------

check_every_setting_is_documented() {
  local documented=$1 settings=$2 build=$3
  local key
  while read -r key; do
    [[ -n $key ]] || continue
    contains "$key" "$documented" && continue
    contains "$key" "$build" && continue
    fail "Settings reads $key and $ENV_EXAMPLE_FILE does not document it.
    A configurable knob with no label is undiscoverable; add a line (commented
    out is fine -- that is this file's idiom for optional), or, if the value is
    set by the image rather than by a person, declare it in SET_BY_THE_BUILD.
    If the field carries an explicit alias, this guard reads the field name and
    needs teaching -- see settings_keys()."
  done <<<"$settings"
}

# --- 6. Every declaration says why ------------------------------------------

check_every_declaration_has_a_reason() {
  local block=$1 name=$2 key reason
  while read -r key; do
    [[ -n $key ]] || continue
    reason=$(declared_reason "$key" "$block")
    [[ -n ${reason// /} ]] ||
      fail "$key is declared $name with no reason. The reason is the whole point:
    the next person has to be able to read why rather than guess."
  done < <(declared_keys "$block")
}

# --- 7. The deployment sets nothing this application does not read ----------

check_every_infra_key_is_read() {
  local settings=$1 platform=$2 build=$3 key
  while read -r key; do
    [[ -n $key ]] || continue
    contains "$key" "$settings" && continue
    contains "$key" "$platform" && continue
    contains "$key" "$build" && continue
    fail "$INFRA_DIR sets $key on a container and Settings never reads it.
    A deployment that sets a name the application does not read configures
    nothing, and the application falls back to a default nobody chose -- which is
    invisible until something is deployed. Either rename it to the Settings field
    it was meant to be, add the field, or declare it in PLATFORM_ENV with the
    reason something other than Settings reads it. This is B-120."
  done < <(infra_env_keys)
}

# --- 8. A selected backend gets what it needs -------------------------------
readonly BACKEND_REQUIRES='
SECRETS_BACKEND | keyvault | KEY_VAULT_URL
ARTIFACTS_BACKEND | blob | ARTIFACTS_ACCOUNT_URL
AUTH_MODE | entra | OIDC_AUTHORITY
'

check_selected_backends_have_what_they_need() {
  local infra_keys line key want companion
  infra_keys=$(infra_env_keys)
  while IFS='|' read -r key want companion; do
    key=${key// /}; want=${want// /}; companion=${companion// /}
    [[ -n $key ]] || continue
    contains "$key" "$infra_keys" || continue
    [[ $(infra_value_for "$key") == "$want" ]] || continue
    contains "$companion" "$infra_keys" && continue
    fail "$INFRA_DIR sets $key=$want and does not set $companion.
    The backend is chosen and the address it needs is missing, so the deployed
    application boots and then refuses the first request that reaches that
    backend. Set $companion in the same template."
  done <<<"$BACKEND_REQUIRES"
}

# --- 9. The deployment can actually answer a question -----------------------
readonly RUN_REQUIRED='
LLM_PROVIDERS | the ordered provider chain a run resolves a model from
LLM_MODELS | provider -> tier -> model id; without it every run fails at its first model call
'

# What makes this a coupling rather than a blanket requirement.
readonly RUN_CREDENTIALS='OPENAI_API_KEY ANTHROPIC_API_KEY'

check_the_deployment_can_answer_a_question() {
  local infra_keys credential found='' key why
  infra_keys=$(infra_env_keys)
  for credential in $RUN_CREDENTIALS; do
    contains "$credential" "$infra_keys" && found=$credential && break
  done
  [[ -n $found ]] || return 0

  while IFS='|' read -r key why; do
    key=${key// /}
    [[ -n $key ]] || continue
    contains "$key" "$infra_keys" && continue
    fail "$INFRA_DIR sets $found and does not set $key --${why}.
    The credential is there and the configuration that makes it usable is not, so
    the deployed API boots, answers /healthz and refuses every question a person
    asks it -- which reaches them as \"The run could not be completed.\" Set $key
    in the same template."
  done <<<"$RUN_REQUIRED"
}

run_checks() {
  local host_only_block=$1 build_block=$2
  local documented compose settings host_only build
  documented=$(documented_keys)
  compose=$(compose_keys)
  settings=$(settings_keys)
  host_only=$(declared_keys "$host_only_block")
  build=$(declared_keys "$build_block")

  [[ -n $documented ]] || fail "$ENV_EXAMPLE_FILE documents no keys at all — is the path right?"
  [[ -n $compose ]] || fail "$COMPOSE_FILE expands no variables at all — is the path right?"

  check_every_documented_key_reaches_a_service "$documented" "$compose" "$host_only" "$build"
  check_declarations_are_not_stale "$documented" "$host_only"
  check_declarations_are_not_contradicted "$compose" "$host_only"
  check_every_passed_key_is_documented "$documented" "$compose" "$build"
  check_every_setting_is_documented "$documented" "$settings" "$build"
  check_every_declaration_has_a_reason "$host_only_block" HOST_ONLY
  check_every_declaration_has_a_reason "$build_block" SET_BY_THE_BUILD
  check_every_infra_key_is_read "$settings" "$(declared_keys "$PLATFORM_ENV")" "$build"
  check_every_declaration_has_a_reason "$PLATFORM_ENV" PLATFORM_ENV
  check_selected_backends_have_what_they_need
  check_the_deployment_can_answer_a_question
}

# --- Selftest ---
# Run before the check it tests, like `check_status.sh --selftest` and...

SELFTEST_WORKSPACE=''
cleanup_workspace() { [[ -n $SELFTEST_WORKSPACE ]] && rm -rf "$SELFTEST_WORKSPACE"; return 0; }

selftest() {
  local passed=0 failed=0 workspace
  SELFTEST_WORKSPACE=$(mktemp -d)
  workspace=$SELFTEST_WORKSPACE
  trap cleanup_workspace EXIT

  expect() {
    local want=$1 name=$2
    shift 2
    local got=0
    ( "$@" ) >/dev/null 2>&1 || got=1
    if [[ $got == "$want" ]]; then
      printf '  ok    %s\n' "$name"
      passed=$((passed + 1))
    else
      printf '  FAIL  %s (expected exit %s, got %s)\n' "$name" "$want" "$got"
      failed=$((failed + 1))
    fi
  }

  # A minimal repo that passes: one key passed to a service, one declared.
  write_fixture() {
    local dir=$1
    mkdir -p "$dir"
    cat >"$dir/.env.example" <<'FIXTURE'
PASSED_KEY=value
# OPTIONAL_KEY=
HOST_KEY=value
FIXTURE
    cat >"$dir/compose.yml" <<'FIXTURE'
services:
  api:
    environment:
      PASSED_KEY: ${PASSED_KEY:-}
      OPTIONAL_KEY: ${OPTIONAL_KEY:-}
      # A comment about ${COMMENTED_KEY:?} is prose, not a variable.
FIXTURE
    cat >"$dir/config.py" <<'FIXTURE'
class Settings(BaseSettings):
    model_config = SettingsConfigDict()
    passed_key: str = "x"
    optional_key: str | None = None


def other() -> None:
    pass
FIXTURE
    # An empty infra directory by default: the existing cases are about compose and Settings.
    mkdir -p "$dir/infra"
  }

  # Runs this script against a fixture, with HOST_KEY declared unless told not to.
  guard() {
    local dir=$1 declaration=${2-'HOST_KEY | A host tool reads it.'}
    ENV_EXAMPLE_FILE="$dir/.env.example" \
      COMPOSE_FILE="$dir/compose.yml" \
      SETTINGS_FILE="$dir/config.py" \
      INFRA_DIR="$dir/infra" \
      SELFTEST_HOST_ONLY="$declaration" \
      bash "${BASH_SOURCE[0]}" --with-declaration
  }

  local dir="$workspace/clean"
  write_fixture "$dir"
  expect 0 "a repo where every key is passed or declared passes" guard "$dir"

  dir="$workspace/undeclared"
  write_fixture "$dir"
  printf 'FORGOTTEN_KEY=value\n' >>"$dir/.env.example"
  expect 1 "a documented key passed to nothing and declared nowhere fails" guard "$dir"

  dir="$workspace/stale"
  write_fixture "$dir"
  expect 1 "a declaration naming a key that no longer exists fails" \
    guard "$dir" 'HOST_KEY | A host tool reads it.
GONE_KEY | Removed two phases ago.'

  dir="$workspace/contradicted"
  write_fixture "$dir"
  expect 1 "a declared key that compose passes anyway fails" \
    guard "$dir" 'HOST_KEY | A host tool reads it.
PASSED_KEY | Claimed host-only while compose passes it.'

  dir="$workspace/undocumented"
  write_fixture "$dir"
  printf '      MYSTERY_KEY: ${MYSTERY_KEY:-}\n' >>"$dir/compose.yml"
  expect 1 "a compose variable nobody documented fails" guard "$dir"

  dir="$workspace/unlabelled"
  write_fixture "$dir"
  # Written whole rather than appended to.
  {
    echo 'class Settings(BaseSettings):'
    echo '    passed_key: str = "x"'
    echo '    optional_key: str | None = None'
    echo '    undocumented_field: str = "x"'
  } >"$dir/config.py"
  expect 1 "a Settings field with no .env.example line fails" guard "$dir"

  dir="$workspace/reasonless"
  write_fixture "$dir"
  expect 1 "a declaration with no reason fails" guard "$dir" 'HOST_KEY |'

  # The parser's own two traps, both of which would make the guard pass everything.
  dir="$workspace/comments"
  write_fixture "$dir"
  expect 0 "a commented example line counts as documented" guard "$dir"

  dir="$workspace/prose"
  write_fixture "$dir"
  printf '      # ${PROSE_KEY:-} appears only in a comment\n' >>"$dir/compose.yml"
  expect 0 "a variable named only inside a compose comment is not a reference" guard "$dir"

  # B-120's cases. The first is the defect itself.
  dir="$workspace/infra-unread"
  write_fixture "$dir"
  cat >>"$dir/infra/apps.bicep" <<'FIXTURE'
            {
              name: 'MYSTERY_ENV'
              value: 'x'
            }
FIXTURE
  expect 1 "an infra env name Settings never reads fails" guard "$dir"

  dir="$workspace/infra-backend"
  write_fixture "$dir"
  cat >>"$dir/infra/apps.bicep" <<'FIXTURE'
            {
              name: 'SECRETS_BACKEND'
              value: 'keyvault'
            }
FIXTURE
  {
    echo 'SECRETS_BACKEND=local'
  } >>"$dir/.env.example"
  {
    echo '      SECRETS_BACKEND: ${SECRETS_BACKEND:-local}'
  } >>"$dir/compose.yml"
  {
    echo 'class Settings(BaseSettings):'
    echo '    passed_key: str = "x"'
    echo '    optional_key: str | None = None'
    echo '    secrets_backend: str = "local"'
  } >"$dir/config.py"
  expect 1 "a backend selected in infra without its companion fails" guard "$dir"

  dir="$workspace/infra-clean"
  write_fixture "$dir"
  cat >"$dir/infra/apps.bicep" <<'FIXTURE'
            {
              name: 'PASSED_KEY'
              value: 'x'
            }
FIXTURE
  expect 0 "a template setting only names Settings reads passes" guard "$dir"

  # B-126, reproduced.
  dir="$workspace/infra-credential-without-models"
  write_fixture "$dir"
  cat >"$dir/infra/apps.bicep" <<'FIXTURE'
            {
              name: 'OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
FIXTURE
  {
    echo 'OPENAI_API_KEY=sk-x'
    echo 'LLM_PROVIDERS=openai'
    echo 'LLM_MODELS={}'
  } >>"$dir/.env.example"
  {
    echo '      OPENAI_API_KEY: ${OPENAI_API_KEY:-}'
    echo '      LLM_PROVIDERS: ${LLM_PROVIDERS:-}'
    echo '      LLM_MODELS: ${LLM_MODELS:-}'
  } >>"$dir/compose.yml"
  {
    echo 'class Settings(BaseSettings):'
    echo '    passed_key: str = "x"'
    echo '    optional_key: str | None = None'
    echo '    openai_api_key: str | None = None'
    echo '    llm_providers: tuple[str, ...] = ()'
    echo '    llm_models: dict[str, str] = {}'
  } >"$dir/config.py"
  expect 1 "a template with a model credential and no model configuration fails" guard "$dir"

  # The control for the case above: the same template, complete.
  dir="$workspace/infra-credential-with-models"
  write_fixture "$dir"
  cat >"$dir/infra/apps.bicep" <<'FIXTURE'
            {
              name: 'OPENAI_API_KEY'
              secretRef: 'openai-api-key'
            }
            {
              name: 'LLM_PROVIDERS'
              value: 'openai'
            }
            {
              name: 'LLM_MODELS'
              value: '{"openai":{"small":"s"}}'
            }
FIXTURE
  {
    echo 'OPENAI_API_KEY=sk-x'
    echo 'LLM_PROVIDERS=openai'
    echo 'LLM_MODELS={}'
  } >>"$dir/.env.example"
  {
    echo '      OPENAI_API_KEY: ${OPENAI_API_KEY:-}'
    echo '      LLM_PROVIDERS: ${LLM_PROVIDERS:-}'
    echo '      LLM_MODELS: ${LLM_MODELS:-}'
  } >>"$dir/compose.yml"
  {
    echo 'class Settings(BaseSettings):'
    echo '    passed_key: str = "x"'
    echo '    optional_key: str | None = None'
    echo '    openai_api_key: str | None = None'
    echo '    llm_providers: tuple[str, ...] = ()'
    echo '    llm_models: dict[str, str] = {}'
  } >"$dir/config.py"
  expect 0 "the same template with its model configuration passes" guard "$dir"

  printf 'check_env --selftest: %d passed, %d failed\n' "$passed" "$failed"
  ((failed == 0))
}

case "${1-}" in
--selftest)
  selftest
  ;;
--with-declaration)
  # Selftest only: run the checks against the declaration the fixture supplied rather than this...
  run_checks "${SELFTEST_HOST_ONLY-}" ''
  ((failures == 0)) || exit 1
  ;;
"")
  run_checks "$HOST_ONLY" "$SET_BY_THE_BUILD"
  if ((failures == 0)); then
    printf 'check_env: %s and %s agree\n' "$ENV_EXAMPLE_FILE" "$COMPOSE_FILE"
  else
    exit 1
  fi
  ;;
*)
  printf 'usage: %s [--selftest]\n' "$0" >&2
  exit 2
  ;;
esac
