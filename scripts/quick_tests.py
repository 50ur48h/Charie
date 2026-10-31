# The quick tests: runs the tests for the areas changed on this branch.
# Used by hand and by the Stop hook. The map comes from docs/architecture/08.
import json
import os
import re
import subprocess
import sys

# Automatic runs never call real AI: replays only, and live_ai tests are left
# out (they also need the practice database, so practice_db is left out too).
# Explicitly authorized live test runs are started by hand, never from here.
BACKEND_TEST = 'uv run --directory backend pytest -q -m "not live_ai and not practice_db" '
FRONTEND_TEST = "npm --prefix frontend test"
FRONTEND_E2E = "npm --prefix frontend run e2e:mock"
# Discovery prompts are tested through the suites that run their jobs.
PROMPT_TESTS = {
    "find_business_terms": "tests/integration/learner/test_business_terms.py",
    "find_dimensions": "tests/integration/knowledge/test_dimension_proofs.py",
    "write_term_recipe": "tests/integration/learner/test_recipes.py",
    "propose_defaults": "tests/integration/learner/test_defaults.py",
    "write_owner_questions": "tests/integration/learner/test_make_questions.py",
}


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
        target = PROMPT_TESTS.get(job)
        if target is not None:
            commands.add(BACKEND_TEST + target)
        else:
            commands.add(BACKEND_TEST + f"tests/integration -k {job}")
    elif p.startswith("backend/tests/questions/"):
        commands.add(BACKEND_TEST + "tests/unit/questions")
    elif p.startswith("backend/charie/shared/"):
        rest = p[len("backend/charie/shared/") :]
        if "/" in rest:
            folder = rest.split("/")[0]
            commands.add(BACKEND_TEST + f"tests/unit/{folder}")
            commands.add(BACKEND_TEST + f"tests/integration/{folder}")
        else:
            commands.add(BACKEND_TEST + "tests/unit/shared")
            commands.add(BACKEND_TEST + "tests/integration/shared")
    elif p.startswith("backend/migrations/"):
        commands.add(BACKEND_TEST + "tests/unit/shared")
        commands.add(BACKEND_TEST + "tests/integration/shared")
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


class DiscoveryError(Exception):
    pass


def git_output(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        raise DiscoveryError(f"git {' '.join(args)} could not run: {exc}")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise DiscoveryError(
            f"git {' '.join(args)} failed: {detail[0] if detail else 'unknown error'}"
        )
    return result.stdout


def changed_files():
    files = set()
    base = git_output(["merge-base", "HEAD", "main"]).strip()
    if base:
        files.update(git_output(["diff", "--name-only", base]).splitlines())
    files.update(git_output(["ls-files", "--others", "--exclude-standard"]).splitlines())
    return sorted(f for f in files if f)


def _target_missing(command):
    """A pytest target with no test dir has nothing to run (generic rules only)."""
    if "pytest" not in command:
        return False
    targets = re.findall(r"tests/\S+", command)
    return bool(targets) and not any(
        os.path.isdir(os.path.join("backend", target))
        or os.path.isfile(os.path.join("backend", target))
        for target in targets
    )


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
        if _target_missing(command):
            continue
        ready.append(command)
    return ready


def run_commands(commands):
    env = dict(os.environ)
    env["AI_REPLAY"] = "replay"
    failed = []
    for command in commands:
        print(f"$ {command}")
        result = subprocess.run(command, shell=True, env=env)
        if result.returncode != 0:
            failed.append(command)
    return failed


def stop_reason(hook_payload, status, detail=""):
    # Never block twice in a row: the session would loop forever. Allowing a
    # stop that was already blocked once is not a claim that tests passed.
    if hook_payload.get("stop_hook_active"):
        return None
    if status == "passed":
        return None
    if status == "failed":
        return "The quick tests failed. Fix the tests first, then finish."
    return (
        f"The quick tests could not run ({detail}). "
        "Fix that first, then finish. Unrun tests are not a pass."
    )


def self_test():
    cases = [
        ("backend/charie/shared/safety/sql_check.py", ["tests/unit/safety"]),
        ("backend/charie/shared/text/numbers.py", ["tests/unit/text", "tests/integration/text"]),
        ("backend/charie/shared/config.py", ["tests/unit/shared", "tests/integration/shared"]),
        ("frontend/shared/src/components/Button.tsx", ["npm", "test"]),
        ("frontend/chat/src/pages/Chat.tsx", ["npm", "e2e:mock"]),
        ("backend/charie/prompts/plan_round.md", ["tests/integration", "plan_round"]),
        (
            "backend/charie/prompts/find_business_terms.md",
            ["tests/integration/learner/test_business_terms.py"],
        ),
        (
            "backend/charie/prompts/find_dimensions.md",
            ["tests/integration/knowledge/test_dimension_proofs.py"],
        ),
        ("backend/tests/questions/format.py", ["tests/unit/questions"]),
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

    backend_command = " ".join(commands_for("backend/charie/shared/safety/x.py"))
    if "not live_ai" not in backend_command or "not practice_db" not in backend_command:
        failed.append("backend commands must exclude live_ai and practice_db")

    real_run = run_commands([f'"{sys.executable}" -c "import sys; sys.exit(3)"'])
    if len(real_run) != 1:
        failed.append("a command exiting 3 must be reported as failed")

    original_run = subprocess.run
    captured = {}

    class FakeResult:
        returncode = 0

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return FakeResult()

    try:
        subprocess.run = fake_run
        if run_commands(["pytest -q tests/unit/safety"]):
            failed.append("a command exiting 0 must pass")
        if captured.get("env", {}).get("AI_REPLAY") != "replay":
            failed.append("test subprocesses must get AI_REPLAY=replay")
        if "tests/unit/safety" not in str(captured.get("command", "")):
            failed.append("test subprocess must receive the planned command")

        def failing_run(*args, **kwargs):
            raise OSError("git is missing")

        subprocess.run = failing_run
        try:
            changed_files()
            failed.append("a git exception must fail discovery")
        except DiscoveryError:
            pass

        class GitFail:
            returncode = 128
            stdout = ""
            stderr = "fatal: not a git repository"

        subprocess.run = lambda *a, **k: GitFail()
        try:
            changed_files()
            failed.append("a git exit 128 must fail discovery")
        except DiscoveryError:
            pass
    finally:
        subprocess.run = original_run

    if stop_reason({"stop_hook_active": True}, "failed") is not None:
        failed.append("stop_hook_active must prevent a second block (loop)")
    if not stop_reason({"stop_hook_active": False}, "failed"):
        failed.append("failed tests must block the first stop")
    if not stop_reason({"stop_hook_active": False}, "error", "git failed"):
        failed.append("unrun tests must block the first stop, never pass silently")
    if stop_reason({"stop_hook_active": False}, "passed") is not None:
        failed.append("passing tests must not block stopping")

    if failed:
        print("self-test failed: " + "; ".join(failed))
        return 1
    print(f"self-test passed ({len(cases) + 8} cases)")
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

    try:
        commands = planned_commands()
    except DiscoveryError as exc:
        print(f"Quick tests could not work out what changed: {exc}")
        if is_stop_hook:
            reason = stop_reason(hook_payload, "error", str(exc))
            if reason:
                print(json.dumps({"decision": "block", "reason": reason}))
            else:
                print("Quick tests did not run (see above); not a pass.")
            return 0
        return 1
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
        print(
            f"Quick tests failed ({len(failed)} of {len(commands)} commands). Fix the tests first."
        )
        if is_stop_hook:
            reason = stop_reason(hook_payload, "failed")
            if reason:
                print(json.dumps({"decision": "block", "reason": reason}))
            return 0
        return 1
    print(f"Quick tests passed ({len(commands)} commands).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
