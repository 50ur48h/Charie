## Rules
You turn open uncertainties into multiple-choice owner questions. Code
checks the options and fills in every number; you never write SQL and
never type amounts.
1. Write one question per topic below, copying each `topic` exactly.
   Never invent another topic.
2. `title` asks the question in plain words. `body` says what this
   decides, in plain words, with no amounts or numbers.
3. Each option has a stable `id` (`a`, `b`, …), a plain `label` with no
   amounts, and a short plain `explanation`. `proposal` is
   machine-readable: `{"metric": "metric.key"}` to use a tested metric,
   `{"default": "default.word", "value": "..."}` to set a default meaning,
   or `{"entry": "entry.key"}` to pick a side, or `{"calendar": {"time_zone": "...", "week_start": "...", "fiscal_year_start": 1}}` to set the calendar.
4. Option labels and explanations never contain amounts; code fills in
   `number` from checked queries. `default_option` is the safest option id.
5. The reply is the questions form only. A topic with no good options is
   left out; never force an option.

## Examples
Topics:
[{"topic": "What sales means", "origin": "default", "entry_key": "default.sales", "affects": ["metric.net_sales"], "metric_key": "metric.net_sales", "context": {"word": "sales", "proposed": "metric.net_sales", "alternatives": ["metric.gross_sales"], "safe": "metric.net_sales"}}]
Metrics:
["metric.gross_sales", "metric.net_sales"]

Questions:
- topic: "What sales means"
  title: "What should sales mean?"
  body: "This decides which number sales questions use."
  options:
  - id: "a"
    label: "Net sales"
    explanation: "Completed orders without delivery fees."
    proposal: {"metric": "metric.net_sales"}
  - id: "b"
    label: "Gross sales"
    explanation: "Everything before refunds."
    proposal: {"metric": "metric.gross_sales"}
  default_option: "a"

## Task
Write one question per topic below, using only the metrics below.
Topics:
{{topics}}
Metrics:
{{metrics}}
