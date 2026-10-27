# The quick tests: runs the tests for the areas changed on this branch.
# Used by hand and by the Stop hook. The map comes from docs/architecture/08.
import json
import os
import subprocess
import sys

BACKEND_TEST = "uv run --directory backend pytest -q "
FRONTEND_TEST = "npm --prefix frontend test"
FRONTEND_E2E = "npm --prefix frontend run e2e:mock"


def commands_for(path):
    p = path.replace("\\", "/")
    commands = set()
    if p.startswith("backend/charie/shared/safety/"):
        commands.add(BACKEND_TEST + "tests/unit/safety")
    elif p.startswith("backend/charie/shared/ai/"):
        commands.add(BACKEND_TEST + "tests/unit/ai")
    elif p.startswith("backend/charie/learner/"):
        commands.add(BACKEND_TEST + "tests/unit/learner")
        commands.add(BACKEND_TEST + "tests/integration/learner")
    elif p.startswith("backend/charie/chat/"):
        commands.add(BACKEND_TEST + "tests/unit/chat")
        commands.add(BACKEND_TEST + "tests/integration/chat")
    elif p.startswith("backend/charie/prompts/") and p.endswith(".md"):
        job = p.rsplit("/", 1)[-1][:-3]
        commands.add(BACKEND_TEST + f"tests/integration -k {job}")
    elif p.startswith("backend/tests/questions/"):
        commands.add(BACKEND_TEST + "tests/unit/questions")
    elif p.startswith("backend/"):
        commands.add(BACKEND_TEST + "tests/unit")
    elif p.startswith("frontend/shared/"):
        commands.add(FRONTEND_TEST)
    elif p.startswith("frontend/chat/") or p.startswith("frontend/learner/"):
        # Until P01.8 defines per-app scripts, run all Vitest plus the mock screens.
        commands.add(FRONTEND_TEST)
        commands.add(FRONTEND_E2E)
    elif p.startswith("frontend/"):
        commands.add(FRONTEND_TEST)
    return commands


def changed_files():
    files = set()
    try:
        base = subprocess.run(
            ["git", "merge-base", "HEAD", "main"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        if base:
            out = subprocess.run(
                ["git", "diff", "--name-only", base],
                capture_output=True, text=True, timeout=30,
            ).stdout
            files.update(out.splitlines())
        out = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=30,
        ).stdout
        files.update(out.splitlines())
    except Exception:
        pass
    return sorted(f for f in files if f)


def planned_commands():
    commands = set()
    for path in changed_files():
        commands.update(commands_for(path))
    ready = []
    for command in sorted(commands):
        if command.startswith("uv run") and not os.path.isfile("backend/pyproject.toml"):
            continue
        if command.startswith("npm") and not os.path.isfile("frontend/package.json"):
            continue
        ready.append(command)
    return ready


def run_commands(commands):
    failed = []
    for command in commands:
        print(f"$ {command}")
        result = subprocess.run(command, shell=True)
        if result.returncode != 0:
            failed.append(command)
    return failed


def self_test():
    cases = [
        ("backend/charie/shared/safety/sql_check.py", ["tests/unit/safety"]),
        ("frontend/shared/src/components/Button.tsx", ["npm", "test"]),
        ("frontend/chat/src/pages/Chat.tsx", ["npm", "e2e:mock"]),
        ("backend/charie/prompts/plan_round.md", ["tests/integration", "plan_round"]),
        ("docs/STATUS.md", []),
        ("", []),
    ]
    failed = []
    for path, expected in cases:
        commands = commands_for(path) if path else set()
        joined = " ".join(commands)
        if expected and not all(part in joined for part in expected):
            failed.append(path)
        if not expected and commands:
            failed.append(path)
    if failed:
        print("self-test failed: " + "; ".join(failed))
        return 1
    print(f"self-test passed ({len(cases)} cases)")
    return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()

    hook_payload = None
    if not sys.stdin.isatty():
        try:
            hook_payload = json.loads(sys.stdin.read() or "null")
        except Exception:
            hook_payload = None
    is_stop_hook = bool(hook_payload) and hook_payload.get("hook_event_name") == "Stop"
    if is_stop_hook and hook_payload.get("stop_hook_active"):
        return 0

    commands = planned_commands()
    if "--dry-run" in sys.argv:
        if not commands:
            if not os.path.isfile("backend/pyproject.toml"):
                print("No back end yet; nothing to test.")
            else:
                print("nothing to test")
            return 0
        for command in commands:
            print(command)
        return 0

    if not commands:
        print("nothing to test")
        return 0
    failed = run_commands(commands)
    if failed:
        print(f"Quick tests failed ({len(failed)} of {len(commands)} commands). "
              "Fix the tests first.")
        if is_stop_hook:
            print(json.dumps({
                "decision": "block",
                "reason": "The quick tests failed. Fix the tests first, then finish.",
            }))
            return 0
        return 1
    print(f"Quick tests passed ({len(commands)} commands).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
