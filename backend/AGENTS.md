# Charie back end: rules for Muse Code

Read the top AGENTS.md first. This file adds the back-end rules; where they conflict, this file wins.

## What's here
- `charie/shared/`: config, db, auth, settings, `ai/`, `connectors/`, `safety/`, `calc/`, `knowledge/`, `jobs/`, `text/` — used by both apps.
- `charie/learner/`: the learner API (`app.py`, `api/`), the learner job (`job.py`) and its steps (`steps/`).
- `charie/chat/`: the chat API (`app.py`, `api/`), the analyst (`analyst/`) and chat memory (`memory.py`).
- `charie/prompts/`: one `.md` file per AI job.
- `tests/unit/`, `tests/integration/`, `tests/questions/`, `tests/replays/` (saved AI replies, not in git).
- `migrations/`: Alembic table changes. `pyproject.toml`: the one Python project (uv).

## Rules
1. Every data shape is a Pydantic model: requests, responses, AI forms, settings and JSON columns.
2. Every AI call goes through `charie.shared.ai`. Never call the `openai` library anywhere else. (From P05.7.)
3. Every query on the customer's database goes through the connector (`charie.shared.connectors`) and `charie.shared.safety.sql_check`. (From P05.11 and P05.12.)
4. All math on numbers goes through `charie.shared.calc` (DuckDB). (From P05.14.)
5. Every number shown to a person is formatted by `charie.shared.text.numbers`. (From P05.6.)
6. Table changes happen only through Alembic migrations in `backend/migrations/`. (From P05.2.)
7. Unit tests never call real AI or the practice database. Use the fake AI client. Tests that need either one get the `live_ai` or `practice_db` marker.
8. Errors for people are plain English, in the shape `{ "error": "code", "message": "…" }`.
9. Prompts live in `charie/prompts/<job>.md`, one file per AI job.

## Tests
- `charie/shared/safety/` → `tests/unit/safety/` · `charie/shared/ai/` → `tests/unit/ai/`
- `charie/shared/<folder>/` → `tests/unit/<folder>/` + `tests/integration/<folder>/`
- any other file in `charie/shared/`, and `backend/migrations/` → `tests/unit/shared/` + `tests/integration/shared/`
- `charie/learner/` → `tests/unit/learner/` + `tests/integration/learner/`
- `charie/chat/` → `tests/unit/chat/` + `tests/integration/chat/`
- `charie/prompts/<job>.md` → the integration tests that use that job, in replay mode
- `backend/tests/questions/` changes → `tests/unit/questions/`
- Markers: `practice_db` (needs the practice database on this laptop) and `live_ai` (makes a real, paid AI call). Both are left out of GitHub's checks; every test that needs either one must carry its marker.

## Commands
`uv sync` · `uv run pytest -q tests/unit` · `uv run pytest -m "not practice_db and not live_ai"` · `uv run ruff format .` · `uv run ruff check .` · `uv run alembic upgrade head`
