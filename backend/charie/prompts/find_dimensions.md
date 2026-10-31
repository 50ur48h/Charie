## Rules
You propose the splits each business number needs, from learned columns only.
1. Propose splits only for the terms below, and only from the columns
   below. Never invent a table, a column, or a term key.
2. Each split names one real column: `table` is one of the tables below
   as `schema.table`, `column` is one of its columns below.
3. `label_column` names the column people read instead of the raw value,
   on the same table, or stays empty. A label must be real too.
4. `grain` splits by time: one of `day`, `week`, `month`, `quarter` or
   `year`, and only on a date column. Anything else leaves grain empty.
5. Propose what the term's splits ask for: a "by restaurant" split needs
   the restaurant column, a "by month" split needs the month grain on a
   date column. Leave a split out when no column fits it.
6. Propose at most 50 splits. The reply is the splits form only; no
   splits means an empty list.

## Examples
Tables:
[{"name": "shop.orders"}]
Columns:
[
  {"name": "shop.orders.status", "type": "text"},
  {"name": "shop.orders.created_at", "type": "timestamp with time zone"},
  {"name": "shop.restaurants.name", "type": "text"}
]
Proposals:
[
  {
    "key": "term.net_sales",
    "name": "Net sales",
    "splits": ["by month", "by restaurant"]
  }
]

Splits:
- term: "term.net_sales"
  table: "shop.orders"
  column: "created_at"
  label_column: ""
  grain: "month"
- term: "term.net_sales"
  table: "shop.restaurants"
  column: "name"
  label_column: ""
  grain: ""

## Task
Propose the splits for each term below, from the columns below.
Tables:
{{tables}}
Columns:
{{columns}}
Proposals:
{{proposals}}
