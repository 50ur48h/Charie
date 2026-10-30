---
name: run-test-questions
description: Ask Charie the test questions and score the answers (smoke, public, hidden or one kind; replayed or fresh). Shows the score table and the cost, saves the report, and supports score overrides after spot-checking.
---

# Run test questions

Rules at the top, always:

- Never open, list or copy anything in `docs/hidden-tests/`, and never put a path inside it on a command line.
- Never repeat hidden question text, even if the owner types it.
- Never add `--yes` without the owner's "yes" in this conversation.
- Never edit a report file by hand; overrides go through `override.py`.
- The skill runs and reports. It doesn't fix answers; fixing is planned work (Phase 13).

1. **Read the arguments.** The set is `smoke`, `public` (the default) or `hidden`. Filters: `kind=<kind>` and `ids=<id,id>`. The mode is `--dry-run`, `fresh`, or neither (replay). Or the whole command is `override <id> <points> "<reason>"`.
2. **Build the command,** run in `backend/`: `uv run python -m tests.questions.run --set <set>`, plus `--kind`, `--ids` and `--dry-run` as asked.
3. **Fresh runs:**
   1. Run the command with `--fresh --estimate`.
   2. Ask the owner, in these words: "This fresh run will cost about $X–Y. Type yes to go on."
   3. Go on only if the whole reply is "yes". Otherwise say "Nothing was run." and stop.
   4. **15 questions or fewer:** run it with `--fresh --yes`. **More than 15:** give the owner the command (without `--yes`) to run in their own PowerShell, and stop. Long runs (an hour or more) shouldn't depend on a Muse Code session staying open; the runner asks for the yes again there.
4. **Show the output as it is,** plus the report's path for public runs.
5. **Spot-check** (public runs that aren't dry runs):
   1. From the new report's `.json`, pick 3 questions: every `wrong` one first, then `partly` ones, then any others.
   2. For each, show the id, the `chat` lines, the question, the answer text, the points and the reasons.
   3. Ask: "Do you want to change any of these scores? Tell me the id, the points and why."
   4. Run step 6 for each change.
6. **Override:** `uv run python -m tests.questions.override --latest <set> --id <id> --points <points> --reason "<reason>"`. The set is `hidden` when the id looks like `h07`, else `public`.
7. **Hidden runs:** after the run, say "Your report is in docs/hidden-tests/reports/. Spot-check it there. To change a score, tell me the id, the points and why." Then use step 6. Never read the report.
