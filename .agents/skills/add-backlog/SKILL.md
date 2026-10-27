---
name: add-backlog
description: Add work found while building — but not part of the current sub-phase — to docs/BACKLOG.md with the next ID and an order number. It never starts the work.
---

# Add backlog

Follow the rules in `docs/BACKLOG.md`:

1. Use the next free `B0xx` ID (IDs are never reused). Give it a type (`bug`, `feature`, `improvement`, `tech-debt`, `docs`, `question`), the sub-phase it was found in, a size, and a plain-English "Done when".
2. Place it in the "Open items" table by order (1 = do first); items below it move down by one. A `bug` that breaks something already merged gets order 1 and status `next`.
3. Add its detail section under "Item details": what it is, why it matters, done when, and notes.
4. Never slip the work into the current PR. Each backlog item later gets its own branch (`b012-short-name`) and PR (`B012: …`), or is folded into a planned sub-phase with /record-change at a phase backlog review.
5. Say, in the session reply, the new backlog ID and its order.
