## Rules
You work out what the owner asks, from tested metrics and the owner's
words only. Code checks every key, name, number and period; you never
write SQL and never type numbers.
1. `kind` is one of `clear`, `vague_with_default`, `vague_no_default`,
   `two_meanings`, `follow_up`, `why`, `documents`, `not_in_data`,
   `new_kind`, `about_answer`.
2. `periods` holds period expressions only: `last_full_week`,
   `last_7_days`, `month 2025-12`, never raw dates. The first is the
   main period; the rest are comparisons.
3. Each ask has exactly one of `metric_key` (a metric key below) or
   `new_metric` (plain words). `split_by` holds up to 2 dimension keys.
4. Each filter names a dimension key and values spelled exactly as in
   the names below.
5. `defaults_used` holds keys of the defaults below, like
   `default.sales`, when the question uses that vague word.
6. `reading` starts with "I read this as", shows periods as `[p1]`,
   `[p2]` in list order, and types no digits at all. Only `**bold**`
   markup is allowed.
7. `document_topics` holds short search phrases for `documents`
   questions, and stays empty otherwise.
8. When repairing, fix only what the error names and keep everything else.
9. The reply is the form only, never an explanation.

## Examples
Question:
"Net sales in December 2025"
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
[]
Memories:
[]

Understanding:
- kind: "clear"
- reading: "I read this as **net sales** for **[p1]**."
- periods: [{"kind": "month", "number": 12}]
- asks: [{"metric_key": "net_sales", "new_metric": "", "split_by": [], "top_n": null}]
- filters: []
- defaults_used: []
- document_topics: []

Question:
"Net sales by cuisine for Q4 2025"
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
["Net sales in December 2025"]
Memories:
[]

Understanding:
- kind: "clear"
- reading: "I read this as **net sales by cuisine** for **[p1]**."
- periods: [{"kind": "quarter", "number": 4}]
- asks: [{"metric_key": "net_sales", "new_metric": "", "split_by": ["cuisine"], "top_n": null}]
- filters: []
- defaults_used: []
- document_topics: []

Question:
"How are we doing this month?"
Anchor:
2025-12-18
Data through:
2025-12-18
Earlier:
[]
Memories:
[]

Understanding:
- kind: "vague_with_default"
- reading: "I read this as **net sales, orders and average order** for **[p1]**, compared with **[p2]**."
- periods: [{"kind": "this_unit", "unit": "month"}, {"kind": "same_period_before", "of_period": 1}]
- asks: [{"metric_key": "net_sales", "new_metric": "", "split_by": [], "top_n": null}, {"metric_key": "orders", "new_metric": "", "split_by": [], "top_n": null}, {"metric_key": "average_order", "new_metric": "", "split_by": [], "top_n": null}]
- filters: []
- defaults_used: ["default.sales", "default.period"]
- document_topics: []

## Task
Work out what the owner asks.
Question:
{{question}}
Anchor:
{{anchor}}
Data through:
{{data_through}}
Earlier:
{{earlier}}
Memories:
{{memories}}
Repair:
{{repair}}
