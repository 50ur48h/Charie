# AGENTS.md — Charie

Charie has two deployables: `apps/web` (Next.js) and `apps/api` (FastAPI).
The analysis engine, connectors and DAL are libraries inside the API.
Read `docs/architecture.md` before making design changes.

MERGE_POLICY: ASK

## Git workflow

- Start from freshly fetched `origin/main` on a new branch. Never commit or push to main.
- Push the branch and open a PR using `.github/pull_request_template.md`.
- Only the owner reviews and squash-merges. Never merge, enable auto-merge,
  or change branch protection on the owner's behalf.
- Check open PRs and red CI before starting work. Rebase on main to resolve conflicts.
- No AI attribution in commits or PRs. Enable `git config core.hooksPath .githooks`.
- Update CHANGELOG for visible changes. Record deferred work in an issue or PR.
- Internal planning documents are no longer maintained in this repository.
  Do not recreate docs/plan or require its files in checks.

## Design and validation

- The architecture is binding. Explain and document design changes in the PR.
- DAL and infrastructure changes require human review.
- The model is never a security boundary; analysis queries go through the DAL.
- Every model called at runtime is a Meta model (Meta Model API). Do not add other
  model or embedding providers.
- The API uses charie_app: no superuser, BYPASSRLS or schema ownership.
  Migrations use the separate owner connection. Never collapse those roles.
- New tenant tables require RLS, a TENANT_TABLES entry and tenant-isolation proofs.
- Prove new behavior is reached through the actual product path, not just a helper.
- When changing a model-filled schema, sweep producers in src, ops and tests.
- Run checks appropriate to the change. Include manual verification steps and
  expected results in the PR, including the failure case.
- Existing TODO(B-###) identifiers remain historical references. Never remove
  security checks.
- Comments and docstrings are one line. Put longer reasoning in the PR.
  Exception: Pydantic model docstrings reach the model as schema text.

## Commands and local development

- Python 3.12 via uv in apps/api; Node 22 and pnpm in apps/web.
- make up / make down: start / stop the local Compose stack.
- make seed rebuilds the generated pizza sample; do not run against user data.
- make db.setup: migrations and the restricted local app login.
- make lint / make typecheck / make test; make preflight lists broader checks.
- On Windows, run Make from Git Bash. Never repurpose HOME or CODEX_HOME.
- Bind-mount reloads can miss host edits. Restart the API after source changes;
  clear /app/.next in the web container before restarting it for code changes.
  New dependencies require rebuilding the relevant image.
- Web tests under memory pressure: use --no-file-parallelism --pool=threads.
- Run API test suites separately: conftest modules and cluster-wide role setup
  can collide. Re-run setup errors in isolation; investigate repeatable failures.
- Git Bash rewrites leading slash arguments. Use MSYS_NO_PATHCONV where needed.
- Do not reset local databases, reseed user data or stop unrelated services
  unless the user has authorized it.

## Data and credentials

- The GitHub repository is public: https://github.com/50ur48h/Charie.
- Never commit secrets. Real credentials stay in local .env or a secret store;
  .env.example contains placeholders and documents runtime configuration.
- Exception: apps/api/src/charie/ops/bootstrap.py publishes the read-only login to the
  synthetic demo database on purpose, so the image runs with only a Meta API key.
- Customer databases, dictionaries, derived findings and diagnostic artifacts
  belong under gitignored .SampleData/. Never publish identifying information.
- Check quoted literals in SQL/view definitions and fixtures as well as data rows.
- Product/repository name is Charie. Keep internal charie identifiers,
  package paths and service names. The Compose project is charie.
- No license has been selected. Do not add license headers or grant permissions.
