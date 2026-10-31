## Rules
You propose one recipe per business number below, from learned columns only.
Code fills in the joins, the time column type, the checks, the SQL preview
and the test date; you never write SQL.
1. Propose recipes only for the terms below, one per term at most. Never
   invent a table, a column, or a term key.
2. `table` is the term's own table below as `schema.table`. `expression`
   adds up or counts that table's columns only (`table.column`, or `*`
   for a plain count). `time_column` is that table's date column below.
3. `aggregate` is `sum`, `count` or `count_distinct`. `filters` keep rows
   with plain comparisons (`table.column = 'value'`); never write joins,
   sub-queries or functions.
4. A `ratio` divides two simple recipes by their term keys (`numerator`,
   `denominator`); it takes no table, aggregate, expression or filters.
5. `unit` is `money`, `count`, `percent` or `ratio`. `currency` is the
   three-letter code for money, else empty.
6. `steps_in_words` says how the number is worked out in two to six plain
   steps. `dimensions` lists the term's split keys below, or stays empty.
7. Propose at most 25 recipes. The reply is the recipes form only; no
   recipe means an empty list. When repairing, fix only what the error
   names and keep everything else.

## Examples
Terms:
[{"key": "term.net_sales", "name": "Net sales", "meaning": "Completed order totals without delivery fees.", "unit": "money"}]
Columns:
[{"name": "shop.orders.total_amount", "type": "numeric"}, {"name": "shop.orders.created_at", "type": "timestamp with time zone"}, {"name": "shop.orders.status", "type": "text"}]
Splits:
[{"term": "term.net_sales", "key": "dimension.month"}]

Recipes:
- term: "term.net_sales"
  kind: "simple"
  title: "Net sales"
  table: "shop.orders"
  aggregate: "sum"
  expression: "orders.total_amount"
  filters: ["orders.status = 'completed'"]
  time_column: "orders.created_at"
  unit: "money"
  currency: "USD"
  steps_in_words: ["Add up every completed order total.", "Leave out delivery fees."]
  dimensions: ["dimension.month"]

## Task
Propose the recipes for each term below, from the columns below.
Terms:
{{terms}}
Columns:
{{columns}}
Splits:
{{splits}}
Repair:
{{repair}}
