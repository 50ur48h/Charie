---
name: record-change
description: Record a change to the Charie plan, design or a decision in docs/CHANGES.md and update every document that mentions it, in the same session.
---

# Record change

Follow the rules in `docs/CHANGES.md` ("How to record a change"):

1. Work out the size. Small (one file, nothing else mentions it): just do it, no record. Medium (a document mentions it: a file, name, library, task, scope or number): record it and update every place. Big (anything in DECISIONS.md, the look, scope, cost, security or privacy): ask the owner first, record after the OK.
2. Find every place: search all of `docs/` and the code for the old name or wording. The table "Where each kind of fact lives" in `docs/IMPLEMENTATION-PLAN.md` shows each fact's home.
3. Update every place in the same session: DECISIONS and architecture files, the current and later sub-phase plans, BACKLOG, STATUS, AGENTS.md files, skills, and the code in the current PR.
4. Add a record at the top of `docs/CHANGES.md` with the next free `C0xx` ID, using its record format: date, found in, size, owner OK, what changed (old → new), why, and the list of every file updated.
5. Say, in the session reply, the new change ID and the files updated.
