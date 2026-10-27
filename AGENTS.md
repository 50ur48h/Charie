# Charie: rules for Muse Code

Charie is an AI data and business analyst with two apps that share one knowledge base:
- Learner app: connects the customer's database, documents and owner notes, then learns and tests the business knowledge.
- Chat app: a ChatGPT-style chat that answers business questions with checked numbers.

## Every session
1. Run /start-session. It checks git and any open PR, then reads docs/STATUS.md and the current sub-phase file in docs/plan/.
2. Work on ONE task at a time. Run /plan for it first.
3. End each task with /finish-task. After the last task of a sub-phase, /finish-task opens the PR.
   Then STOP: the owner reviews and merges. While the PR is open, only fix the owner's review comments.

## Where things are
- docs/ (on this laptop only): DECISIONS.md (what we decided; it wins), IMPLEMENTATION-PLAN.md and plan/ (what to build),
  architecture/ (how it's built), designs/calm/ (the approved look), reference/ (checked facts),
  BACKLOG.md (later work), CHANGES.md (every change and where it was updated).
- backend/: Python, FastAPI. Read backend/AGENTS.md.
- frontend/: React. Read frontend/AGENTS.md.
- infra/: Bicep. docker/: Dockerfiles. .github/: PR template and workflows.

## Golden rules
1. The AI never types numbers. AI text uses labels like [n1]; code fills in the numbers.
2. Code does all math (DuckDB) and all checks.
3. The customer's database is read-only. Never write to it. Never change the practice data.
4. Every query goes through the SQL checker. Known business numbers use recipes, not AI-written SQL.
5. Check, don't guess. For Meta, Azure, Muse Code or any library, read the real docs (MCP: microsoft-learn, context7)
   or the installed package. Save short notes in docs/reference/.
6. Small tasks. Each task has a "Done when" test. Don't start the next task until it passes.
7. Tests before done. Don't break what already works. Run the tests for the areas you touched.
8. Everything a user reads is plain, simple English: screens, thinking panel, errors.
9. Simple code. Comments: one or two short lines, only where needed. Use a good existing library before writing your own.
10. Never open or edit .env. Never commit secrets. Never open docs/hidden-tests/.
11. Follow DECISIONS.md. If something seems wrong, ask; don't change it on your own.
12. Match the approved designs in docs/designs/calm/. Use the theme colors, never hard-coded colors.
13. Git: work only on the sub-phase's branch. Never commit or push on main. Never merge, close or approve a PR.
    Never force-push. One open PR at a time.
14. Stay in scope: only what the current sub-phase file says. Anything else goes to docs/BACKLOG.md (/add-backlog).
15. If anything differs from the plan or the docs (a name, a file, a choice), record it with /record-change
    and update every document that mentions it, in the same session.

## Main commands
Back end (in backend/): uv sync · uv run pytest -q tests/unit · uv run ruff check . · uv run alembic upgrade head
Front end (in frontend/): npm install · npm run dev:chat · npm run dev:learner · npm test · npm run lint · npx playwright test
Our database: docker compose up -d db
