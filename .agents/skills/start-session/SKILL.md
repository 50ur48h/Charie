---
name: start-session
description: Start a Charie session — check git and any open PR, handle recovery cases, read the status and current sub-phase, then say where we are and what is next.
---

# Start session

Run these steps in order. State lives in git, the master list and the plan files, never in chat.

1. Dirty tree first: run `git status --porcelain` and `git branch --show-current`.
   - If the branch matches a sub-phase that is `in progress` (or whose branch exists with unticked tasks in its plan file) and every changed file is inside that sub-phase's scope, resume it at its first unticked task. An unfinished sub-phase always beats new plan or backlog work.
   - If the tree is dirty on `main`, or the scope is unclear, stop and list the files. Never stash, discard or commit them without the owner.
2. Check for an open PR: `gh pr list --state open --author @me --json number,title,headRefName,url`.
3. If a PR is open, run `gh pr view <n> --json state,reviews,statusCheckRollup` and `gh api repos/50ur48h/Charie/pulls/<n>/comments`:
   - Failing checks: name them, fix them on the PR's branch (each fix its own commit where practical), push, say what was fixed, then stop.
   - Review comments without our reply: switch to the PR's branch, fix each comment as its own commit, push, reply to each with `gh api -X POST repos/50ur48h/Charie/pulls/<n>/comments/<id>/replies -f body="Fixed in <short sha>: <what changed>"`, then stop.
   - No comments and checks green: say "PR #<n> is waiting for your review" and stop.
4. If no PR is open:
   - `git switch main`, then `git pull --ff-only`.
   - For each sub-phase marked `in review (#N)` in `docs/plan/README.md`, check `gh pr view <N> --json state,headRefOid`:
     - `MERGED`: mark it `done (#N)`. Compare `git rev-parse <branch>` with the PR's `headRefOid`. If they differ, the local branch has later work: never delete it; report the extra commits and ask the owner. If they are equal, delete with `git branch -d`; for a squash-merged PR `-d` cannot see the merge, so `git branch -D` is then allowed — the exact tip match is the safety proof that nothing extra is lost. `git branch --merged main` listing it also allows `-d`.
     - `CLOSED` (not merged): never mark it done and never delete the branch. Keep `in review (#N)`, report it, and ask the owner: reopen, or abandon? Only the owner's answer, recorded with /record-change, changes it.
     - Not found: say so and ask the owner. Never guess a PR was merged.
   - An `in progress` sub-phase or an existing sub-phase branch is resumed before picking anything new (this is how an interrupted or quota-stopped session recovers). Rows marked `in progress (background)` (only P06.4, the owner's hidden questions) are never resumed or picked: skip them here and in step 5, and leave them alone.
5. Pick the next work: a BACKLOG.md item with status `next` comes first. Otherwise pick the next sub-phase per the master list (skipping `in progress (background)` rows), or a batch of 2–3 related sub-phases (C012) whose external Needs are all done. At a phase's first sub-phase, run the phase kickoff in `docs/IMPLEMENTATION-PLAN.md` and wait for the owner's OK.
6. Read the sub-phase file (each included one, for a batch) and every "Read first" file. For a PR, `git switch -c <branch>` or switch to it if it exists. Local and owner sub-phases get no branch.
7. Print exactly this 5-line summary (list every included sub-phase for a batch):
   - Where we are: <phase>, <sub-phase(s) and task position>
   - Git: <branch and state>. Open PR: <none or #N>. Last merged: <sub-phase (#N)>
   - Next task: <the next task>
   - Done when: <its done-when test>
   - Next step: run /plan for this task.

Never merge, close or approve a PR. Never push to `main`. Never force-push.
