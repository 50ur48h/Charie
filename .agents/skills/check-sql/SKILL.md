---
name: check-sql
description: Run a query through Charie's SQL safety checker and explain the result in plain English.
---

# Check SQL

Take one SQL query and run it through `charie.shared.safety.sql_check`:

1. Build the catalog: `Catalog(tables=[...])` with the `public.` tables the question may use, plus any required filters, forbidden tables and average columns from the knowledge base.
2. Run `check_sql(sql, catalog)` and explain the verdict in plain English: allowed or blocked, and why. Name the rule (`one_select`, `allowed_tables`, `functions`, `required_filters`, `counting`, `averaging`, `explicit-columns`, `heavy_query`) only when it helps; the reasons are already plain sentences.
3. When the query is allowed and row counts matter, run `explain_plan(sql, catalog, connector)` on the practice database (read-only) and say what the database's own plan thinks.
4. Never run a blocked query. If it is blocked, say what to change (name the columns, add the required filter, drop the function) instead of running it.

The same check from a shell:

- `uv run python -m charie.shared.safety.check_sql_cli --database URL --catalog FILE --query SQL`
- Add `--explain` for the database's own row estimate, `--max-rows N` for a lower cap, `--list-tables` to print the database's `schema.table` names.
- `uv run python -m charie.shared.safety.list_tables --database URL`
