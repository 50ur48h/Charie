# The formatter: tidies one file right after it is edited (PostToolUse hook).
# The path comes from the command line, or from the hook's stdin JSON. Paths
# are resolved against the repository root, tools run in their own project
# folder, and real failures are reported. It only skips when a tool is
# genuinely unavailable (the project or the program does not exist yet).
import json
import os
import shutil
import subprocess
import sys
import tempfile

SKIP = "Formatter not installed yet; skipping"


def repo_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return os.path.normpath(out.stdout.strip())
    except Exception:
        pass
    return os.getcwd()


def resolve_path(raw, root):
    path = (raw or "").strip()
    for prefix in ("\\\\?\\", "//?/"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    path = path.replace("/", os.sep).replace("\\", os.sep)
    if not os.path.isabs(path):
        path = os.path.join(root, path)
    return os.path.normpath(path)


def actions_for(path, root, which=shutil.which):
    # Returns ("skip", reason) or ("run", [(argv, cwd), ...]).
    lower = path.lower()
    backend_dir = os.path.join(root, "backend")
    frontend_dir = os.path.join(root, "frontend")

    if lower.endswith(".py"):
        if not os.path.isfile(os.path.join(backend_dir, "pyproject.toml")):
            return "skip", "no backend project yet"
        if which("uv") is None:
            return "skip", "uv is not installed"
        return "run", [
            (["uv", "run", "ruff", "format", path], backend_dir),
            (["uv", "run", "ruff", "check", "--fix", path], backend_dir),
        ]

    if lower.endswith((".ts", ".tsx", ".css", ".json")):
        if not (path == frontend_dir or path.startswith(frontend_dir + os.sep)):
            return "skip", "not a frontend file"
        if not os.path.isfile(os.path.join(frontend_dir, "package.json")):
            return "skip", "no frontend project yet"
        if which("npx") is None:
            return "skip", "npx is not installed"
        actions = [(["npx", "prettier", "--write", path], frontend_dir)]
        if lower.endswith((".ts", ".tsx")):
            actions.append((["npx", "eslint", "--fix", path], frontend_dir))
        return "run", actions

    return "skip", "nothing formats this file type"


def run_actions(actions):
    failed = []
    for argv, cwd in actions:
        try:
            result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
        except Exception as exc:
            failed.append(f"{' '.join(argv)} could not run: {exc}")
            continue
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            failed.append(
                f"{' '.join(argv)} exited {result.returncode}: "
                f"{detail[0] if detail else 'no details'}")
    return failed


def hook_path():
    try:
        payload = json.loads(sys.stdin.read() or "")
        tool_input = payload.get("tool_input") or {}
        if tool_input.get("path"):
            return tool_input["path"]
        response = payload.get("tool_response") or {}
        return response.get("filePath", "")
    except Exception:
        return ""


def self_test():
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.normpath(tmp)
        rel = resolve_path("backend/x.py", root)
        if rel != os.path.join(root, "backend", "x.py"):
            failed.append("relative path must resolve against the repo root")
        absolute = os.path.join(root, "frontend", "src", "a.ts")
        if resolve_path(absolute, root) != absolute:
            failed.append("absolute path must stay unchanged")
        prefixed = resolve_path("\\\\?\\" + absolute, root)
        if prefixed != absolute:
            failed.append("long-path prefix must be removed")

        status, _ = actions_for(rel, root, which=lambda name: None)
        if status != "skip":
            failed.append("a .py file without a backend project must skip")

        os.makedirs(os.path.join(root, "backend"))
        open(os.path.join(root, "backend", "pyproject.toml"), "w").close()
        status, _ = actions_for(rel, root, which=lambda name: None)
        if status != "skip":
            failed.append("a .py file without uv must skip")
        status, actions = actions_for(rel, root, which=lambda name: "uv")
        if status != "run" or actions[0][1] != os.path.join(root, "backend"):
            failed.append("ruff must run from the backend folder")
        if "format" not in actions[0][0] or rel not in actions[0][0]:
            failed.append("ruff format must get the resolved file path")

        os.makedirs(os.path.join(root, "frontend", "src"))
        open(os.path.join(root, "frontend", "package.json"), "w").close()
        ts_file = resolve_path("frontend/src/a.ts", root)
        status, actions = actions_for(ts_file, root, which=lambda name: "npx")
        tools = [argv[1] for argv, _ in actions]
        if status != "run" or tools != ["prettier", "eslint"]:
            failed.append("a .ts file needs prettier then eslint, from frontend")
        css_file = resolve_path("frontend/src/a.css", root)
        status, actions = actions_for(css_file, root, which=lambda name: "npx")
        if [argv[1] for argv, _ in actions] != ["prettier"]:
            failed.append("a .css file needs prettier only")
        status, _ = actions_for(
            resolve_path("scripts/a.ts", root), root, which=lambda name: "npx")
        if status != "skip":
            failed.append("a .ts file outside frontend must skip")

    original_run = subprocess.run

    class BadResult:
        returncode = 2
        stderr = "boom"
        stdout = ""

    try:
        subprocess.run = lambda *a, **k: BadResult()
        if not run_actions([(["ruff", "format", "x.py"], ".")]):
            failed.append("a formatter exiting 2 must be reported as a failure")
    finally:
        subprocess.run = original_run

    if failed:
        print("self-test failed: " + "; ".join(failed))
        return 1
    print("self-test passed (10 cases)")
    return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    raw = sys.argv[1] if len(sys.argv) > 1 else hook_path()
    if not raw:
        print(SKIP)
        return 0
    root = repo_root()
    path = resolve_path(raw, root)
    status, payload = actions_for(path, root)
    if status == "skip":
        print(SKIP)
        return 0
    failed = run_actions(payload)
    if failed:
        for failure in failed:
            print(f"Formatter failed: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
