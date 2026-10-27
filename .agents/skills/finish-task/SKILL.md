---
name: finish-task
description: Finish one Charie task — run the right tests, tick the plan, update the status, and commit. After the last task of a sub-phase (or batch), run every local check, push, and open the PR.
---

# Finish task

1. Safety: if `git branch --show-current` prints `main`, stop and say so. Never commit on `main`.
2. Run the quick tests for the areas this task touched: `python scripts/quick_tests.py`. Fix any failure before going on. Nothing is "done" while its tests fail.
3. Ask: did anything differ from the sub-phase file (a name, a file, a choice)? If yes, run /record-change first and update every document that mentions it.
4. Tick the task in its sub-phase file. Rewrite `docs/STATUS.md`. Save any lesson worth keeping to memory (facts about tools go in `docs/reference/`).
5. Commit only this task's files, by name: `git add <files>`, then `git commit -m "<ID>: <what this commit does>"`. One task, one commit.
6. If this was not the last task, stop here and say what the next task is.

After the last task of a sub-phase (or of the last sub-phase in a batch):

7. Run every local check: all unit and integration tests, the practice-database and live-AI tests if the sub-phase needs them (say their result in the PR), and the screen tests for any touched app. Take the screenshots the sub-phase asks for.
8. Write the sub-phase entry in `docs/PROGRESS.md`. Set each finished sub-phase to `in review` in `docs/plan/README.md` (the PR number is added once known; use `in review (#N)` after step 10).
9. Push the branch: `git push -u origin <branch>`.
10. Open the PR: `gh pr create --title "<first ID>: <what it does>" --body-file .temp/pr-body.md`. The body follows `.github/pull_request_template.md` and, for a batch, lists every included sub-phase with its finished tasks. Update the master list to `in review (#N)`.
11. Watch the checks: `gh pr checks --watch`. If a check fails, fix it on the same branch, push, and watch again.
12. When all checks are green, say "PR #N is ready for your review" and stop. Never merge, close or approve the PR.
