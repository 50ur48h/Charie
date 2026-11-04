# Charie — developer entry points.

.DEFAULT_GOAL := help

# These recipes need a POSIX shell.
SHELL_PROBE := $(shell sh -c "echo yes" 2>&1)
ifneq ($(SHELL_PROBE),yes)
$(error No POSIX shell found, so these recipes cannot run. Use Git Bash, or add Git's usr\bin to PATH first: $$env:PATH = 'C:\Program Files\Git\usr\bin;' + $$env:PATH)
endif
SHELL := sh

GIT_SHA := $(shell git rev-parse HEAD 2>/dev/null)

API_DIR := apps/api
UV_API  := uv run --directory $(API_DIR)

WEB_DIR := apps/web
PNPM_WEB := pnpm --dir $(WEB_DIR)

COMPOSE := docker compose --env-file .env -f ops/docker-compose.yml

# --- Meta ---
.PHONY: help
help: ## Show available targets
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

.PHONY: env
env: .env ## Create .env from .env.example if it does not exist

.env:
	@cp .env.example .env
	@printf 'Created .env from .env.example. Local-only values; review before use.\n'

# --- Umbrella targets ---
.PHONY: install lint fmt typecheck test
install: install.api install.web         ## Install all dependencies
lint: lint.api lint.web lint.seed        ## Lint everything
fmt: fmt.api                             ## Format everything in place
typecheck: typecheck.api typecheck.web   ## Type-check everything
test: test.api test.web                  ## Run all tests

# --- Local stack ---
.PHONY: up up.mssql down down.hard logs ps seed seed.mssql seed.definitions
up: .env ## Start the app and platform database (no sample data)
	$(COMPOSE) up -d --build
	@printf '\n  web  http://localhost:3000\n  api  http://localhost:8000/healthz\n\n'

up.mssql: .env ## Start the SQL Server container on demand (Phase 3+)
	$(COMPOSE) --profile mssql up -d mssql

down: ## Stop the stack, keeping database volumes
	$(COMPOSE) down

down.hard: ## Stop the stack and delete its volumes (throws away seeded data)
	$(COMPOSE) down --volumes

logs: ## Follow logs from every service
	$(COMPOSE) logs -f

ps: ## Show stack status
	$(COMPOSE) ps

seed: .env ## (Re)build the pizza demo dataset in seed-pizza-pg
	uv run ops/seed/seed_pizza.py

seed.mssql: .env ## (Re)build the pizza demo dataset in the mssql container
	$(SHELL) ops/scripts/seed_mssql.sh

seed.definitions: .env ## Load metric definitions: make seed.definitions FILE=... SOURCE="..."
	$(SHELL) ops/scripts/seed_definitions.sh

.PHONY: db.setup migrate migrate.down migration
db.setup: .env ## Migrate, then give charie_app its local login
	$(SHELL) ops/scripts/db_setup.sh

migrate: .env ## alembic upgrade head against the local platform database
	$(UV_API) alembic upgrade head

migrate.down: .env ## Roll back one revision
	$(UV_API) alembic downgrade -1

migration: .env ## Autogenerate a revision: make migration m="add widgets"
	$(UV_API) alembic revision --autogenerate -m "$(m)"

.PHONY: secrets.key
secrets.key: ## Print a fresh LOCAL_SECRETS_KEY line to paste into .env
	@$(UV_API) python -c "from cryptography.fernet import Fernet; print('LOCAL_SECRETS_KEY=' + Fernet.generate_key().decode())"

#   check.todos   — `TODO(B-###)` or CI fails.
.PHONY: preflight
preflight: lint typecheck check.env check.todos check.roles check.truths check.preflight lint.workflows test test.rls test.dal test.web.e2e compile.web check.infra build.infra ## Every CI step that needs no stack or cloud session
	@echo ""
	@echo "Preflight clean — every CI step that runs without a stack, a registry"
	@echo "or a cloud session. CI will additionally run, and this did not:"
	@echo "  gitleaks            a GitHub Action; no local equivalent is wired up"
	@echo "  mssql connectors    needs the SQL Server container (make up.mssql)"
	@echo "  evals               needs the platform DB and the pizza fixture"
	@echo "  coverage floor      combines two CI shards; neither exists here"
	@echo "  test.web.smoke      builds images and seeds a database; minutes"
	@echo "  docker images       both prod builds"
	@echo ""

.PHONY: check.preflight
check.preflight: ## Fail if ci.yml grew a step preflight neither runs nor excuses
	$(UV_API) python ../../scripts/check_preflight.py --selftest
	$(UV_API) python ../../scripts/check_preflight.py

.PHONY: check.todos check.roles lint.workflows
check.todos: ## Fail if a TODO carries no backlog id
	bash scripts/check_todos.sh

check.roles: ## Fail if a role id and the secret-scanner allowlist disagree (B-130)
	sh ops/scripts/check_role_definitions.sh --allowlist-only

# `MSYS_NO_PATHCONV=1` because Git Bash rewrites `-w /repo` into `C:/Program Files/Git/repo` and...
lint.workflows: ## actionlint over every workflow, with shellcheck on each `run:` block
	MSYS_NO_PATHCONV=1 docker run --rm -v "$(CURDIR):/repo" -w /repo \
	  rhysd/actionlint:latest@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667 \
	  -color

.PHONY: check.env
check.env: ## Fail if a documented variable reaches no container and nothing says why
	bash scripts/check_env.sh --selftest
	bash scripts/check_env.sh

.PHONY: check.infra
check.infra: ## Fail if a secret value is written into a deployment template
	bash scripts/check_infra_secrets.sh --selftest
	bash scripts/check_infra_secrets.sh

.PHONY: build.infra
build.infra: ## Compile every Bicep module and both parameter files
	$(SHELL) ops/scripts/build_infra.sh

.PHONY: truths check.truths
truths: ## Regenerate ops/seed/truths.json without touching the database
	uv run ops/seed/seed_pizza.py --truths-only

check.truths: ## Fail if truths.json and the seed generator disagree
	uv run ops/seed/seed_pizza.py --check

# --- apps/api ---
# `--no-cache` on every lint recipe, deliberately.
.PHONY: install.api lint.api fmt.api typecheck.api test.api test.rls test.dal test.llm api.dev build.api llm.smoke agent.smoke
install.api: ## Sync the API virtualenv from uv.lock
	uv sync --directory $(API_DIR)

lint.api: ## ruff check + format check
	$(UV_API) ruff check --no-cache .
	$(UV_API) ruff format --check --no-cache .

fmt.api: ## ruff format + autofix
	$(UV_API) ruff format .
	$(UV_API) ruff check --fix .

typecheck.api: ## pyright (strict)
	$(UV_API) pyright

test.api: ## pytest with coverage
	$(UV_API) pytest --cov --cov-report=term-missing

test.rls: ## Tenant-isolation proof suite on its own; fails if it collects nothing
	$(UV_API) pytest -m rls_proof

test.dal: ## The security boundary's suite, with its own coverage gate (plan §4.4)
	$(UV_API) pytest tests/dal --cov=charie.dal --cov-report=term-missing --cov-fail-under=90

test.llm: ## The LLM package's suite on its own
	$(UV_API) pytest tests/llm

llm.smoke: ## Live provider smoke — real keys, real money, NEVER in CI
	$(UV_API) python ../../scripts/llm_smoke.py $(ARGS)

agent.smoke: ## Live agent smoke — one real question end to end, NEVER in CI
	$(UV_API) python ../../scripts/agent_smoke.py $(ARGS)

api.dev: ## uvicorn with reload on :8000
	$(UV_API) uvicorn charie.main:app --host 0.0.0.0 --port 8000 --reload

build.api: ## Build the production API image
	docker build --target prod --build-arg GIT_SHA=$(GIT_SHA) -t charie-api:local $(API_DIR)

# --- ops/seed — a standalone uv script, so it has its own dependencies and is not ---
.PHONY: lint.seed
lint.seed: ## ruff check the seed scripts
	$(UV_API) ruff check --no-cache --config pyproject.toml ../../ops
	$(UV_API) ruff format --check --no-cache --config pyproject.toml ../../ops

# --- apps/web ---
.PHONY: install.web lint.web typecheck.web test.web test.web.e2e test.web.smoke web.dev build.web compile.web
install.web: ## Install web dependencies from the lockfile
	$(PNPM_WEB) install --frozen-lockfile

lint.web: ## eslint
	$(PNPM_WEB) lint

typecheck.web: ## next typegen + tsc --noEmit
	$(PNPM_WEB) typecheck

test.web: ## vitest
	$(PNPM_WEB) test

test.web.e2e: ## Playwright: the chat screen in a real browser, against a stub API
	$(PNPM_WEB) test:e2e

test.web.smoke: .env ## Playwright: the whole product in a browser, on its own compose stack
	$(SHELL) ops/scripts/web_smoke.sh $(ARGS)

web.dev: ## next dev on :3000
	$(PNPM_WEB) dev

compile.web: ## next build — the production compile CI runs after test.web
	$(PNPM_WEB) build

build.web: ## Build the production web image
	docker build --target prod --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 --build-arg NEXT_PUBLIC_ENV=local -t charie-web:local $(WEB_DIR)

.PHONY: trial
trial: .env ## Engine trial: ask each probe 3+ times against a source and compare the runs
	$(UV_API) python -m charie.ops.trial $(ARGS)

.PHONY: evals
evals: .env ## Run the 20 golden evals (FakeLLM by default; EVALS_LIVE=1 for real models)
	$(UV_API) --with pyyaml python ../../ops/evals/runner.py $(ARGS)

evals.docker: .env ## Same, but inside the api container — for the compose stack
	$(SHELL) ops/scripts/evals.sh $(ARGS)

evals.setup: .env ## The eval harness's org — HOST addresses, not usable in the browser (B-115)
	$(UV_API) python ../../ops/evals/provision.py

# Two provisioners, and the difference is the network you are on (B-115).
.PHONY: demo.setup
demo.setup: .env ## The browser's org — COMPOSE addresses, built inside the api container
	$(SHELL) ops/scripts/demo_setup.sh

.PHONY: test.fixtures.up
test.fixtures.up: .env ## Start synthetic databases for tests only
	$(COMPOSE) --profile test-fixtures up -d seed-pizza-pg
