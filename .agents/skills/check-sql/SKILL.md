---
name: check-sql
description: Run a query through Charie's SQL safety checker and explain the result in plain English.
---

# Check SQL

Take one SQL query and check it on the practice database only, through the CLI from `backend/`:

- `uv run python -m charie.shared.safety.check_sql_cli "<SQL>"`
- Add `--count` only when row counts matter; add `--catalog-file <path>` only
  for trying extra rules (see `tests/data/catalog-traps.json`).
- Never run a query any other way, and never on anything but the practice database.

Repeat the first line (the mode line) back, then the verdict: "Allowed." or
"Blocked:" with each numbered reason. Explain each reason in one or two plain
sentences, and suggest a fixed query when a reason says how (name the columns,
add the required filter, sum first in a sub-query, drop the function).
