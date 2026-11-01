## Rules
You write practice questions that check Charie's business numbers. Code
runs everything; you never write SQL and never type amounts.
1. Write one practice question per metric below, up to `{{count}}`
   questions. Never invent another metric.
2. `question` asks the question in plain words, with no amounts or numbers.
3. `metric` is the metric key below, copied exactly.
4. `period_start` and `period_end` are dates like 2025-11-01. The start is
   never after the end.
5. `splits` lists dimension keys from that metric's `dimensions` below, or
   is empty for a plain total. Never invent a split.
6. The reply is the questions form only. A metric with no good question is
   left out; never force a question.

## Examples
Metrics:
[{"key": "metric.net_sales", "title": "Net sales", "unit": "money", "dimensions": ["restaurant"]}]

Questions:
- question: "What were net sales by restaurant in November 2025?"
  metric: "metric.net_sales"
  period_start: "2025-11-01"
  period_end: "2025-11-30"
  splits: ["restaurant"]
- question: "What were net sales in November 2025?"
  metric: "metric.net_sales"
  period_start: "2025-11-01"
  period_end: "2025-11-30"
  splits: []

## Task
Write up to {{count}} practice questions using only the metrics below.
Metrics:
{{metrics}}
