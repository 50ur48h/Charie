# The formatter: tidies one file right after it is edited (PostToolUse hook).
# The path comes from the command line, or from the hook's stdin JSON.
# Until the tools exist (ruff in P01.7, Prettier in P01.8) it quietly skips.
import json
import os
import subprocess
import sys

SKIP = "Formatter not installed yet; skipping"


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


def run(command):
    try:
        subprocess.run(command, capture_output=True, timeout=120)
    except Exception:
        pass


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else hook_path()
    if not path:
        print(SKIP)
        return 0
    path = path.replace("\\\\?\\", "").replace("\\", "/")
    lower = path.lower()

    if lower.endswith(".py"):
        if not os.path.isfile("backend/pyproject.toml"):
            print(SKIP)
            return 0
        run(["uv", "run", "--directory", "backend", "ruff", "format", path])
        run(["uv", "run", "--directory", "backend", "ruff", "check", "--fix", path])
        return 0

    if lower.endswith((".ts", ".tsx", ".css", ".json")) and "/frontend/" in "/" + lower:
        if not os.path.isfile("frontend/package.json"):
            print(SKIP)
            return 0
        run(["npx", "--prefix", "frontend", "prettier", "--write", path])
        if lower.endswith((".ts", ".tsx")):
            run(["npx", "--prefix", "frontend", "eslint", "--fix", path])
        return 0

    print(SKIP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
