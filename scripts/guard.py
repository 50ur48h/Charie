# The guard: blocks dangerous actions before they happen (PreToolUse hook).
# Standard library only. It is a guardrail for Muse Code's own tool calls;
# the practice database's real protection is its read-only login.
import json
import re
import subprocess
import sys

SAFE_BLOCK = "Guard couldn't read this action, so it was blocked to be safe."


def norm_path(path):
    return (path or "").replace("\\", "/").lower()


def check_file(path, action):
    p = norm_path(path)
    name = p.rsplit("/", 1)[-1]
    if "docs/hidden-tests/" in p or p.startswith("docs/hidden-tests/"):
        return ("Blocked: the owner's hidden test questions are off-limits. "
                "Work from the public questions and the plan instead.")
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return ("Blocked: .env files hold secrets and are never opened or edited. "
                "Use .env.example to see the setting names.")
    return None


def check_command(command, branch):
    cmd = " ".join((command or "").lower().split())

    if re.search(r"\bdrop\s+database\b", cmd) or re.search(r"\bdropdb\b", cmd):
        return ("Blocked: dropping a database is never allowed. "
                "If a database must go, ask the owner to do it.")
    if re.search(r"\bdocker\s+(volume\s+)?rm\b", cmd) and "charie_restaurant_demo" in cmd:
        return ("Blocked: the practice database container and its data must not be removed. "
                "Leave charie_restaurant_demo alone.")
    if "charie_demo" in cmd and re.search(
            r"\b(insert|update|delete|drop|alter|truncate|create)\b", cmd):
        return ("Blocked: the practice database is read-only and its data never changes. "
                "Only read from it, with the charie_readonly login.")

    if re.search(r"\bgh\s+pr\s+merge\b", cmd):
        return ("Blocked: Muse Code never merges PRs. "
                "Tell the owner the PR is ready, and stop.")
    if re.search(r"\bgh\s+pr\s+close\b", cmd):
        return ("Blocked: Muse Code never closes PRs. "
                "Tell the owner, and let them decide.")
    if re.search(r"\bgh\s+pr\s+review\b", cmd) and "--approve" in cmd:
        return ("Blocked: Muse Code never approves PRs. "
                "The owner reviews and merges.")

    if re.search(r"\bgh\s+api\b", cmd):
        if "rulesets" in cmd or "protection" in cmd:
            return ("Blocked: Muse Code never changes GitHub's protection settings. "
                    "Ask the owner to make that change.")
        if re.search(r"(-x\s*delete|--method\s+delete)\b", cmd):
            return "Blocked: Muse Code never deletes things through the GitHub API."
        if re.search(r"pulls/\d+/merge", cmd):
            return ("Blocked: Muse Code never merges PRs. "
                    "Tell the owner the PR is ready, and stop.")

    if re.search(r"\bgit\s+push\b", cmd):
        if re.search(r"(^|\s)(-f|--force|--force-with-lease)(\s|$)", cmd):
            return ("Blocked: force-pushing is never allowed. "
                    "Push normally, or ask the owner if you are stuck.")
        if re.search(r"\bmain\b", cmd):
            return ("Blocked: Muse Code never pushes to main. "
                    "Push the sub-phase branch and open a PR instead.")
        if branch == "main":
            return ("Blocked: you are on main. Switch to the sub-phase branch, "
                    "then push that branch.")

    if branch == "main":
        if re.search(r"\bgit\s+commit\b", cmd):
            return ("Blocked: never commit on main. Switch to the sub-phase branch first.")
        if re.search(r"\bgit\s+merge\b", cmd):
            return ("Blocked: never merge on main. Work happens on the sub-phase branch, "
                    "and the owner merges the PR on GitHub.")
        if re.search(r"\bgit\s+pull\b", cmd) and "--ff-only" not in cmd:
            return "Blocked: on main, only git pull --ff-only is allowed."

    return None


def current_branch():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


MISSING_FILE_INPUT = ("Blocked: this file action has no file path, so the guard "
                      "can't check it. Give the path and try again.")
MISSING_COMMAND_INPUT = ("Blocked: this shell action has no command, so the guard "
                         "can't check it. Give the command and try again.")


def decide(payload):
    if not isinstance(payload, dict):
        return SAFE_BLOCK
    tool = payload.get("tool_name")
    if not tool or not isinstance(tool, str):
        return SAFE_BLOCK
    tool_input = payload.get("tool_input")
    if tool_input is None:
        tool_input = {}
    if not isinstance(tool_input, dict):
        return SAFE_BLOCK
    if tool in ("read_file", "write_file", "edit_file"):
        path = tool_input.get("path")
        if not path or not isinstance(path, str):
            return MISSING_FILE_INPUT
        action = "read" if tool == "read_file" else "edit"
        return check_file(path, action)
    if tool in ("powershell", "powershell_input"):
        command = tool_input.get("command") or tool_input.get("chars")
        if not command or not isinstance(command, str):
            return MISSING_COMMAND_INPUT
        return check_command(command, current_branch())
    if "hidden-tests" in json.dumps(tool_input).lower():
        return ("Blocked: the owner's hidden test questions are off-limits. "
                "Work from the public questions and the plan instead.")
    return None


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


def self_test():
    cases = []

    def file_case(path, action, blocked):
        cases.append((f"{action} {path}", check_file(path, action), blocked))

    def cmd_case(command, branch, blocked):
        cases.append((f"{command} (on {branch})", check_command(command, branch), blocked))

    file_case(".env", "read", True)
    file_case("backend/.env", "read", True)
    file_case(".env.local", "read", True)
    file_case(".env.example", "read", False)
    file_case("docs/hidden-tests/questions.yaml", "read", True)
    file_case("docs/hidden-tests/questions.yaml", "edit", True)

    cmd_case("git commit -m x", "main", True)
    cmd_case("git merge feature", "main", True)
    cmd_case("git pull", "main", True)
    cmd_case("git pull --ff-only", "main", False)
    cmd_case("git switch -c p01.5-x", "main", False)
    cmd_case("git push origin main", "p01.5-guard-and-hooks", True)
    cmd_case("git push origin HEAD:main", "p01.5-guard-and-hooks", True)
    cmd_case("git push", "main", True)
    cmd_case("git push -f", "p01.5-guard-and-hooks", True)
    cmd_case("git push --force", "p01.5-guard-and-hooks", True)
    cmd_case("git push --force-with-lease", "p01.5-guard-and-hooks", True)
    cmd_case("git push -u origin p01.5-guard-and-hooks", "p01.5-guard-and-hooks", False)

    cmd_case("gh pr merge 3", "any", True)
    cmd_case("gh pr close 3", "any", True)
    cmd_case("gh pr review 3 --approve", "any", True)
    cmd_case("gh pr create --title x", "any", False)
    cmd_case("gh pr view 3", "any", False)
    cmd_case("gh pr checks 3", "any", False)
    cmd_case("gh pr list", "any", False)

    cmd_case("gh api -X PUT repos/x/y/pulls/3/merge", "any", True)
    cmd_case("gh api repos/x/y/rulesets", "any", True)
    cmd_case("gh api -X DELETE repos/x/y/issues/1", "any", True)
    cmd_case("gh api --method DELETE repos/x/y/issues/1", "any", True)
    cmd_case("gh api repos/x/y/pulls/3/comments", "any", False)

    cmd_case('psql -c "DROP DATABASE charie"', "any", True)
    cmd_case("dropdb charie", "any", True)
    cmd_case('psql charie_demo -c "INSERT INTO orders VALUES (1)"', "any", True)
    cmd_case('psql charie_demo -c "select count(*) from orders"', "any", False)
    cmd_case("docker rm charie_restaurant_demo-db-1", "any", True)
    cmd_case("docker volume rm charie_restaurant_demo_data", "any", True)
    cmd_case("git status", "main", False)

    payload_cases = [
        ("empty payload", {}, True),
        ("payload is a list", ["read_file"], True),
        ("no tool name", {"tool_input": {"path": ".env"}}, True),
        ("tool_input not an object", {"tool_name": "read_file", "tool_input": "x"}, True),
        ("read without path", {"tool_name": "read_file", "tool_input": {}}, True),
        ("edit with empty path", {"tool_name": "edit_file", "tool_input": {"path": ""}}, True),
        ("shell without command", {"tool_name": "powershell", "tool_input": {}}, True),
        ("shell input without text", {"tool_name": "powershell_input", "tool_input": {"session_id": 1}}, True),
        ("read .env payload", {"tool_name": "read_file", "tool_input": {"path": ".env"}}, True),
        ("read .env.example payload", {"tool_name": "read_file", "tool_input": {"path": ".env.example"}}, False),
    ]
    for name, payload, blocked in payload_cases:
        cases.append((name, decide(payload), blocked))

    failed = [name for name, reason, blocked in cases if (reason is not None) != blocked]
    if failed:
        print("self-test failed: " + "; ".join(failed))
        return 1
    print(f"self-test passed ({len(cases)} cases)")
    return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    try:
        payload = json.loads(sys.stdin.read() or "")
        reason = decide(payload)
    except Exception:
        return deny(SAFE_BLOCK)
    if reason:
        return deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
