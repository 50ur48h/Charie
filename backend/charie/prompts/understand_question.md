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
   and `not_in_data` questions, and stays empty otherwise.
8. When repairing, fix only what the error names and keep everything else.
9. The reply is the form only, never an explanation.
10. Follow-ups point at the chat, never at new words. `inherit` names the
    parts the question takes from the chat's focus: `asks`, `filters`,
    `periods`. `list_refs` holds up to 3 pointers at shown lists: `words`
    are your exact words, `position` is 1 for the first, 2 for the second,
    -1 for the last, `dimension` is a dimension key or null. The reading
    names a listed item only as `{ref1}`, `{ref2}` or `{ref3}`. Code puts
    in the item's name in bold. `period_shift` moves the chat's last
    periods: `unit` is `day`, `week`, `month`, `quarter` or `year`, `n`
    is below 0 for "before". It stays null otherwise. "3 weeks ago"
    counts from today, so it stays a normal period expression.
11. Vague words use their settled default (`vague_with_default`, named in
    `defaults_used`) when the word's entry has a settled meaning. A vague
    word with no settled meaning and exactly 2 fitting metrics is
    `two_meanings`, with both in `meanings` (`label` in your words, one
    `metric_key` each). Any other vague question is `vague_no_default`
    with exactly one `choice`: 2 to 4 options, all ids different, no
    digits in the text or labels. `choice` is only for `vague_no_default`;
    `meanings` only for `two_meanings`. Never ask more than one quick question per question.
12. Saved memories come from the user. When one changes what a word
    means (like 'sales'), follow it, and say so in the reading. A
    message that only states a preference still reads as a question
    about that number for the default period.
13. `about_answer` explains an earlier answer from the chat's notes.
    `about` lists said refs like `812:n1` (the earlier message and
    label as shown in the chat context); empty means the whole last
    answer. Refs you cannot match stay empty. `missing` stays empty.
14. `not_in_data` names what the data doesn't have. `missing` is a
    short phrase with no digits, like "market share". `about`
    stays empty. `document_topics` holds one search phrase for it.

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

Question:
"How did the second one do in 2024?"
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
["Which 5 restaurants had the highest net sales in 2025?"]
Chat context:
Looking at: net_sales; by restaurant; 1 Jan 2025 – 31 Dec 2025
List 1 (newest), "Net sales by restaurant" (restaurant): 1. Downtown Austin 2. Rice, Miller and Gutmann
Memories:
[]

Understanding:
- kind: "follow_up"
- reading: "I read this as **net sales** for {ref1} for **[p1]**."
- periods: [{"kind": "year", "year": 2024}]
- asks: [{"metric_key": "net_sales", "new_metric": "", "split_by": [], "top_n": null}]
- filters: []
- defaults_used: []
- document_topics: []
- inherit: ["filters"]
- list_refs: [{"words": "the second one", "position": 2, "dimension": "restaurant"}]
- period_shift: null

Question:
"Same for last year?"
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
["What were net sales in Q4 2025?"]
Chat context:
Looking at: net_sales; 1 Oct – 31 Dec 2025
Memories:
[]

Understanding:
- kind: "follow_up"
- reading: "I read this as **net sales** for [p1]."
- periods: []
- asks: []
- filters: []
- defaults_used: []
- document_topics: []
- inherit: ["asks"]
- list_refs: []
- period_shift: {"words": "last year", "unit": "year", "n": -1}

Question:
"Which are our best restaurants?"
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
[]
Chat context:
Looking at: delivered orders; 1 Jan 2025 – 31 Dec 2025
Memories:
[]

Understanding:
- kind: "vague_no_default"
- reading: "I read this as best restaurants for [p1]."
- periods: [{"kind": "year", "year": 2025}]
- asks: []
- filters: []
- defaults_used: []
- document_topics: []
- inherit: []
- list_refs: []
- period_shift: null
- choice: {"text": "How should I rank them?", "options": [{"id": "by_net_sales", "label": "By net sales"}, {"id": "by_growth", "label": "By growth"}, {"id": "by_average_order", "label": "By average order"}]}
- meanings: []

Question:
"How are sales doing?"
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
[]
Chat context:
Looking at: delivered orders; 1 Jan 2025 – 31 Dec 2025
Memories:
[]

Understanding:
- kind: "two_meanings"
- reading: "I read this as net sales and gross sales for [p1]."
- periods: [{"kind": "year", "year": 2025}]
- asks: [{"metric_key": "net_sales", "new_metric": "", "split_by": [], "top_n": null}, {"metric_key": "gross_sales", "new_metric": "", "split_by": [], "top_n": null}]
- filters: []
- defaults_used: []
- document_topics: []
- inherit: []
- list_refs: []
- period_shift: null
- choice: null
- meanings: [{"label": "Net sales", "metric_key": "net_sales"}, {"label": "Gross sales", "metric_key": "gross_sales"}]

Question:
"For me, sales means without delivery fees."
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
[]
Chat context:

Memories:
[]

Understanding:
- kind: "vague_with_default"
- reading: "I read this as sales with delivery fees taken out for [p1]."
- periods: [{"kind": "month", "number": 12}]
- asks: [{"metric_key": "net_sales", "new_metric": "", "split_by": [], "top_n": null}]
- filters: []
- defaults_used: ["default.sales"]
- document_topics: []
- inherit: []
- list_refs: []
- period_shift: null
- choice: null
- meanings: []

Question:
"How did you get that?"
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
["What was the delivered order amount in December 2025?"]
Chat context:
Looking at: delivered order amount; 1-31 Dec 2025
Already said: [812:n1] Delivered order amount in 1-31 Dec 2025 = $1.52M;
Memories:
[]

Understanding:
- kind: "about_answer"
- reading: "I read this as how I worked out my last answer."
- periods: []
- asks: []
- filters: []
- defaults_used: []
- document_topics: []
- about: []
- missing: ""
- inherit: []
- list_refs: []
- period_shift: null

Question:
"What is our market share?"
Anchor:
2025-12-31
Data through:
2025-12-31
Earlier:
[]
Chat context:

Memories:
[]

Understanding:
- kind: "not_in_data"
- reading: "I read this as our market share."
- periods: []
- asks: []
- filters: []
- defaults_used: []
- document_topics: ["market share"]
- about: []
- missing: "market share"
- inherit: []
- list_refs: []
- period_shift: null

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
Chat context:
{{chat_context}}
Memories:
{{memories}}
Repair:
{{repair}}
