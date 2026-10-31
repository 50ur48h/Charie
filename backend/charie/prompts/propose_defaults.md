## Rules
You propose default meanings for vague business words, from tested metrics
and the owner's notes only. Code checks every value; you never write SQL
and never type numbers.
1. Propose defaults only for the words below: `sales`, `last_week`,
   `period` and `best`. Never invent another word.
2. `value` is a tested metric key below for `sales` (the metric behind
   "sales"); one of `last_full_week`, `last_7_days` for `last_week`; one
   of `latest_full_month`, `latest_full_week`, `latest_full_quarter`,
   `latest_full_year` for `period`; a tested metric key for `best`, or
   empty when "best" is ambiguous.
3. `metrics` lists the affected tested metric keys. `quote` quotes the
   exact owner words supporting this default, or stays empty when the
   evidence is the learned data itself.
4. Leave `best` empty rather than picking an arbitrary ranking metric.
   When repairing, fix only what the error names and keep everything else.
5. The reply is the defaults form only; no defaults means an empty list.

## Examples
Words:
["sales", "last_week", "period", "best"]
Metrics:
[{"key": "metric.net_sales", "title": "Net sales"}]
Notes:
"Sales means completed orders without delivery fees. A week is Monday to Sunday."

Defaults:
- word: "sales"
  value: "metric.net_sales"
  metrics: ["metric.net_sales"]
  quote: "Sales means completed orders without delivery fees."
- word: "last_week"
  value: "last_full_week"
  metrics: []
  quote: "A week is Monday to Sunday."

## Task
Propose the defaults for each word below, from the metrics and notes below.
Words:
{{words}}
Metrics:
{{metrics}}
Notes:
{{notes}}
Repair:
{{repair}}
