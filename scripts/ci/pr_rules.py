# Checks a pull request's branch name, title and changed files.
# Run by the pr-rules job in .github/workflows/ci.yml. Standard library only.
import os
import re
import subprocess
import sys

BRANCH_PATTERN = re.compile(r"^(p\d{2}\.\d{1,2}[a-z]?|b\d{3})-[a-z0-9]+(-[a-z0-9]+)*$")
TITLE_PATTERN = re.compile(r"^(P\d{2}\.\d{1,2}[a-z]?|B\d{3}): .+$")
MAX_FILE_BYTES = 5 * 1024 * 1024
LINE_WARNING_LIMIT = 800


def valid_branch(branch):
    return bool(BRANCH_PATTERN.match(branch or ""))


def valid_title(title):
    title = title or ""
    return len(title) <= 72 and bool(TITLE_PATTERN.match(title))


def changed_files(base_sha, head_sha):
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_sha}...{head_sha}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    return [line for line in result.stdout.splitlines() if line]


def changed_lines(base_sha, head_sha):
    result = subprocess.run(
        ["git", "diff", "--numstat", f"{base_sha}...{head_sha}"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return 0
    total = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if path.endswith("package-lock.json") or path.endswith("uv.lock"):
            continue
        if "replays/" in path or "__snapshots__/" in path:
            continue
        if added.isdigit():
            total += int(added)
        if deleted.isdigit():
            total += int(deleted)
    return total


def self_test():
    cases = [
        (valid_branch("p01.3-skeleton-and-ci"), True, "branch p01.3-skeleton-and-ci"),
        (valid_branch("p03.2b-thinking-panel"), True, "branch p03.2b-thinking-panel"),
        (valid_branch("b012-chart-labels"), True, "branch b012-chart-labels"),
        (valid_branch("feature/x"), False, "branch feature/x"),
        (valid_branch("P01.3-Caps"), False, "branch P01.3-Caps"),
        (valid_branch("p1.3-short"), False, "branch p1.3-short"),
        (valid_title("P01.3: Repo skeleton"), True, "title P01.3: Repo skeleton"),
        (valid_title("B012: Fix labels"), True, "title B012: Fix labels"),
        (valid_title("P01.3 Repo skeleton"), False, "title without colon"),
        (valid_title("P01.3: " + "x" * 66), False, "title of 73 characters"),
    ]
    failed = [name for got, want, name in cases if got != want]
    if failed:
        print("self-test failed: " + ", ".join(failed))
        return 1
    print("self-test passed")
    return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()

    event = os.environ.get("EVENT", "")
    failures = []

    if event == "pull_request":
        branch = os.environ.get("BRANCH", "")
        if not valid_branch(branch):
            failures.append(
                f"Branch name '{branch}' doesn't match the pattern "
                "p03.2-short-name or b012-short-name"
            )
        title = os.environ.get("PR_TITLE", "")
        if not valid_title(title):
            failures.append(
                f"PR title '{title}' doesn't match the pattern "
                "'P03.2: What it does' (at most 72 characters)"
            )

    base_sha = os.environ.get("BASE_SHA", "")
    head_sha = os.environ.get("HEAD_SHA", "")
    files = changed_files(base_sha, head_sha) if base_sha and head_sha else []
    if files is None:
        failures.append("Could not list the changed files with git diff")
        files = []
    for path in files:
        if path.startswith("docs/"):
            failures.append(f"File '{path}' is from docs/, which never goes to git")
        name = path.rsplit("/", 1)[-1]
        if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
            failures.append(f"File '{path}' looks like a secrets file (.env)")
        if os.path.isfile(path) and os.path.getsize(path) > MAX_FILE_BYTES:
            failures.append(f"File '{path}' is over 5 MB")

    if base_sha and head_sha:
        lines = changed_lines(base_sha, head_sha)
        if lines > LINE_WARNING_LIMIT:
            print(f"::warning::PR changes {lines} lines; aim for 500 or fewer")

    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
