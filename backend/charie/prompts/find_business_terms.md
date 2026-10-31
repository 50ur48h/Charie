## Rules
You propose business numbers worth tracking, from learned evidence only.
1. Propose only numbers the evidence supports: a table and column that
   exist below, a document fact quoted below, or an owner rule named below.
   Never invent a table, a column, a fact or a rule.
2. Name each term the way the business says it, in a few plain words.
3. Units: `money` for amounts of money, `count` for counts of things,
   `percent` for shares out of 100, `ratio` for one number divided by
   another, `quantity` for measured amounts that are not money,
   `duration` for lengths of time, `date` for points in time, `id` for
   identifiers, `code` for short labels, `text` for words, `flag` for
   yes-or-no states, `other` for anything else. Money needs no currency
   here; the recipe step checks that later.
4. Evidence is a short reference, one per line of proof:
   `table:shop.orders` names a table below, `column:shop.orders.status`
   names a column below, `doc:Net sales` names a document fact topic below,
   `rule:Test restaurants never count` names an owner rule below. Every
   reference must match the evidence exactly; an unmatched reference
   rejects the whole term.
5. Splits name how the business may want the number broken down, for
   example "by month" or "by restaurant". Name at most five.
6. Propose at most 25 terms, the most business-critical first. The reply
   is the terms form only; no terms means an empty list.

## Examples
Tables:
[
  {"name": "shop.orders", "meaning": "One row per order the shop took."}
]
Columns:
[
  {
    "name": "shop.orders.status",
    "meaning": "How the order ended: completed or cancelled."
  },
  {
    "name": "shop.orders.total_amount",
    "meaning": "What the customer paid, in dollars.",
    "unit": "money"
  }
]
Rules:
[
  {"title": "Test restaurants never count", "meaning": "Test orders stay out."}
]
Document facts:
[
  {"topic": "Net sales", "statement": "Net sales means completed order totals."}
]

Terms:
- name: "Net sales"
  meaning: "Completed order totals for the period."
  unit: "money"
  evidence:
    - "column:shop.orders.total_amount"
    - "doc:Net sales"
  splits:
    - "by month"
    - "by restaurant"

## Task
Propose the business numbers worth tracking from the evidence below.
Tables:
{{tables}}
Columns:
{{columns}}
Rules:
{{rules}}
Document facts:
{{doc_facts}}
