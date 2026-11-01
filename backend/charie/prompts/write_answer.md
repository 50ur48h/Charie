## Rules
You write the answer as blocks, with labels and never digits.
Code fills in every label and checks the copy.
1. Every number, quote and period is written as its [label] alone: `[n1]`, `[t2]`, `[p1]`, `[q3]`. Never type a value or a bare number, not even a year. Titles and subtitles use labels too, never years.
2. Each `fact` and `conclusion` lists its proof labels. A `possible_reason` must sound possible: use "may", "might", "possibly", "a likely reason" or "could".
3. Text markup only: `**bold**`, `<good>`, `<bad>` and `<mark>`. The direct answer first, then why, then what is worth knowing, then suggestions.
4. A chart or table block names its `[t]` label, with the x and y column keys for a chart. Suggestions carry `likely` or `worth_checking`.
5. Mention every couldn't-check finding and every still-open point in a `note` sentence. Follow the style rules.
6. Answer length: `short` means at most 4 sentences and 1 chart; `normal` a few short paragraphs and up to 2 charts; `detailed` up to 4 charts.
7. The reply is the form only, never an explanation.

## Examples
Question: How are we doing?
Reading: I read this as **net sales, orders and average order** for 1–31 Dec 2025.
Kind: vague_with_default
Notebook:
## Notebook
[n1] = $1.35M: Net sales, 1–31 Dec 2025
[n2] = 25.1K: Orders, 1–31 Dec 2025
[n3] = 54.02: Average order, 1–31 Dec 2025
[p1] = 1–31 Dec 2025 (December 2025)
## END
Still open: none
Couldn't tell: none

Draft:
- type: text, sentences: [{"kind": "fact", "text": "December was a good month: net sales were [n1] on [n2] orders in [p1].", "proof": ["n1", "n2"], "starts_paragraph": true}, {"kind": "conclusion", "text": "The average order was [n3].", "proof": ["n3"], "starts_paragraph": false}]
- type: kpis, kpis: [{"title": "Net sales", "value": "[n1]"}, {"title": "Orders", "value": "[n2]"}, {"title": "Average order", "value": "[n3]"}]
- type: suggestions, suggestions_title: "What I'd do", suggestions: [{"text": "Ask why December beat November.", "confidence": "worth_checking"}]

Question: How did net sales change by restaurant in December?
Reading: I read this as **net sales by restaurant** for 1–31 Dec 2025.
Kind: clear
Notebook:
## Notebook
[t1] = table, 4 rows: Change in net sales by restaurant, Dec vs Nov 2025 (columns: restaurant, change)
Downtown, −18.2%
Uptown, +6.2%
Riverside, +2.1%
Hillcrest, −0.4%
[p1] = 1–31 Dec 2025 (December 2025)
[p2] = 1–30 Nov 2025 (November 2025)
## END
Still open: none
Couldn't tell: none

Draft:
- type: text, sentences: [{"kind": "fact", "text": "Sales moved both ways in [p1].", "proof": ["t1"], "starts_paragraph": true}, {"kind": "possible_reason", "text": "Downtown may explain most of the drop.", "proof": ["t1"], "starts_paragraph": false}]
- type: chart, chart: {"kind": "bar_diverging", "title": "Sales change by restaurant", "subtitle": "[p1] vs [p2]", "table": "[t1]", "x": "restaurant", "y": "change", "highlight": ["Downtown"]}

## Task
Write the answer blocks.
Question:
{{question}}
Reading:
{{reading}}
Kind:
{{kind}}
Notebook:
{{notebook}}
Still open:
{{still_open}}
Couldn't tell:
{{cannot_tell}}
Stop reason:
{{stop_reason}}
Problems:
{{problems}}
Style rules:
{{style_rules}}
Answer length:
{{answer_length}}
Fixes:
{{fixes}}
