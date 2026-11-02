# The real-mode screen-test runner (P12.4): a throwaway copy of our database,
# the run script, and the serve command for debugging and the look check.
#
#   python scripts/e2e_real.py save    # you, once, when the knowledge is good
#   python scripts/e2e_real.py reset   # rebuild charie_e2e from the dump
#   python scripts/e2e_real.py run [--record]
#   python scripts/e2e_real.py serve   # both APIs in replay mode until Ctrl+C
#
# Automatic runs never call real AI: `run` uses AI_REPLAY=replay unless
# --record is passed, and --record needs your explicit yes (about $5-15).
# The script only ever drops `charie_e2e`; anything else refuses.
import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO / "backend"
FRONTEND_DIR = REPO / "frontend"
DUMP_PATH = BACKEND_DIR / "tests" / "replays" / "e2e-db.dump"
READY_PATH = BACKEND_DIR / "tests" / "replays" / "e2e-journeys.ready"

E2E_DB = "charie_e2e"
CHAT_PORT = 8001
LEARNER_PORT = 8002
E2E_PASSWORD = "e2e-password"

sys.path.insert(0, str(BACKEND_DIR))


def fail(message: str) -> None:
    print(f"e2e_real: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_db_url(raw: str) -> dict:
    """Split a SQLAlchemy Postgres URL into its connection parts."""
    if not raw:
        fail("DATABASE_URL is not set. Start with: docker compose up -d db")
    url = urlparse(raw.replace("+psycopg", "").replace("+psycopg2", ""))
    if not url.hostname or not url.path.lstrip("/"):
        fail(f"DATABASE_URL is not a usable Postgres URL: {raw!r}")
    return {
        "user": url.username or "charie",
        "password": url.password or "",
        "host": url.hostname,
        "port": str(url.port or 5432),
        "database": url.path.lstrip("/"),
    }


def real_db_url() -> str:
    """Our own database URL, from the back end's settings."""
    from charie.shared.config import get_settings

    raw = get_settings().database_url
    if not raw:
        fail("DATABASE_URL is not set. Start with: docker compose up -d db")
    return raw


def e2e_db_url() -> str:
    """The throwaway test database URL: same server, fixed safe name."""
    base = real_db_url()
    head, _, _ = base.rpartition("/")
    return f"{head}/{E2E_DB}"


def check_guard(name: str) -> None:
    """Refuse to drop anything but the throwaway test database."""
    if name != E2E_DB:
        fail(f"refusing to drop {name!r}: this script only ever drops {E2E_DB!r}")


def compose(
    *args: str, input_bytes: bytes | None = None, env: dict | None = None
) -> None:
    """Run `docker compose` from the repo root; the DB must be up."""
    try:
        subprocess.run(
            ["docker", "compose", *args],
            cwd=REPO,
            input=input_bytes,
            env=env,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        fail("docker is not installed or not on PATH.")
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        fail(
            f"`docker compose {' '.join(args)}` failed: {detail[-1] if detail else err}"
        )


def server_url(raw: str) -> str:
    """The bare server URL for one database URL (for CREATE/DROP DATABASE)."""
    parts = urlparse(raw.replace("+psycopg", "").replace("+psycopg2", ""))
    return f"{parts.scheme}://{parts.netloc}/postgres"


def cmd_save() -> None:
    """Dump our database for the journeys. You run this once, by hand."""
    from charie.shared.tables.knowledge import KbVersion
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    parts = parse_db_url(real_db_url())
    engine = create_engine(server_url(real_db_url()))
    with Session(engine) as session:
        published = session.scalars(
            select(KbVersion).where(KbVersion.status == "published")
        ).all()
        drafts = session.scalars(
            select(KbVersion).where(KbVersion.status == "draft")
        ).all()
    engine.dispose()
    if len(published) != 1 or drafts:
        fail(
            "save needs exactly one published version and no draft waiting: "
            f"found {len(published)} published, {len(drafts)} draft."
        )
    env = dict(os.environ, PGPASSWORD=parts["password"])
    dump = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "pg_dump",
            "-Fc",
            "-U",
            parts["user"],
            "-d",
            parts["database"],
        ],
        cwd=REPO,
        env=env,
        check=False,
        capture_output=True,
    )
    if dump.returncode != 0:
        detail = dump.stderr.decode("utf-8", "replace").strip().splitlines()
        fail(f"pg_dump failed: {detail[-1] if detail else dump.returncode}")
    DUMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    DUMP_PATH.write_bytes(dump.stdout)
    # New knowledge means new fingerprints: old journey recordings go stale.
    if READY_PATH.exists():
        READY_PATH.unlink()
    print(f"e2e database saved to {DUMP_PATH} ({len(dump.stdout)} bytes).")


def scrub_e2e_database(url: str) -> int:
    """Clean a restored throwaway database for the journeys.

    Deletes every chat (with its messages, thinking lines, notebook and
    query runs), every memory and every learner to-do item; flips the
    published version back to draft; resets the settings the journeys
    need. Returns the version number waiting to be published.
    """
    from argon2 import PasswordHasher
    from charie.shared.settings import get_setting, set_setting
    from charie.shared.tables.chat import Chat, Memory, NotebookItem, QueryRun
    from charie.shared.tables.knowledge import KbVersion
    from charie.shared.tables.questions import LearnerTodo
    from sqlalchemy import create_engine, delete, select
    from sqlalchemy.orm import Session

    engine = create_engine(url)
    with Session(engine) as session:
        # Journeys publish and add chats: start from a clean slate.
        session.execute(delete(Chat))
        session.execute(delete(Memory))
        session.execute(delete(LearnerTodo))
        session.execute(delete(QueryRun))
        session.execute(delete(NotebookItem))
        published = session.scalars(
            select(KbVersion).where(KbVersion.status == "published").limit(1)
        ).one_or_none()
        version_number = 0
        if published is not None:
            version_number = published.number
            published.status = "draft"
            published.published_at = None
        for key, value in [
            ("theme", "sage"),
            ("memory_on", True),
            ("show_reading", True),
            ("number_format", "short"),
            ("spend_limit_usd", 150),
            ("spend_warn_percent", 80),
            ("setup_done", False),
            ("password_hash", PasswordHasher().hash(E2E_PASSWORD)),
        ]:
            set_setting(session, key, value)
        session.commit()
        assert get_setting(session, "setup_done") is False
        assert get_setting(session, "theme") == "sage"
    engine.dispose()
    return version_number


def cmd_reset() -> None:
    """Rebuild the throwaway database from the dump, ready for the journeys."""
    from sqlalchemy import create_engine

    if not DUMP_PATH.is_file():
        fail(
            f"no dump at {DUMP_PATH}: run `python scripts/e2e_real.py save` "
            "once first, when the knowledge is in a good state."
        )
    url = e2e_db_url()
    parts = parse_db_url(url)
    check_guard(parts["database"])
    engine = create_engine(server_url(url), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        from sqlalchemy import text

        conn.execute(text(f'DROP DATABASE IF EXISTS "{E2E_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{E2E_DB}"'))
    env = dict(os.environ, PGPASSWORD=parts["password"])
    compose(
        "exec",
        "-T",
        "db",
        "pg_restore",
        "-U",
        parts["user"],
        "-d",
        E2E_DB,
        "--no-owner",
        input_bytes=DUMP_PATH.read_bytes(),
        env=env,
    )
    version_number = scrub_e2e_database(url)
    print(
        f"e2e database ready: version {version_number} waiting to be published, setup not done"
    )


def _wait_for_health(port: int, timeout_seconds: int = 60) -> None:
    """Wait until one API answers /api/health, or fail."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{port}/api/health", timeout=5
            ) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(1)
    fail(f"the API on port {port} never became healthy.")


def _start_api(app: str, port: int, extra_env: dict) -> "subprocess.Popen":
    env = dict(os.environ, DATABASE_URL=e2e_db_url(), **extra_env)
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"charie.{app}.app:app", "--port", str(port)],
        cwd=BACKEND_DIR,
        env=env,
    )


def _stop(services: list) -> None:
    for service in services:
        if service.poll() is None:
            service.terminate()
    for service in services:
        try:
            service.wait(timeout=15)
        except subprocess.TimeoutExpired:
            service.kill()


def _npx() -> list:
    if os.name == "nt":
        return ["cmd", "/c", "npx"]
    return ["npx"]


def _run_playwright(project: str, recording: bool = False) -> int:
    env = dict(os.environ)
    if recording:
        # The specs record instead of skipping while this is set.
        env["E2E_RECORDING"] = "1"
    return subprocess.run(
        [
            *_npx(),
            "playwright",
            "test",
            "-c",
            "playwright.real.config.ts",
            f"--project={project}",
        ],
        cwd=FRONTEND_DIR,
        env=env,
        check=False,
    ).returncode


def cmd_run(record: bool) -> None:
    """Reset, start both APIs, run the journeys, stop. Stops at first failure."""
    if record:
        print("e2e_real: recording fresh replies (this spends about $5-15).")
    started = time.monotonic()
    if record:
        cmd_reset()
        services = [
            _start_api("chat", CHAT_PORT, {"AI_REPLAY": "record"}),
            _start_api("learner", LEARNER_PORT, {"AI_REPLAY": "record"}),
        ]
        try:
            _wait_for_health(CHAT_PORT)
            _wait_for_health(LEARNER_PORT)
            code = _run_playwright("laptop", recording=True)
        finally:
            _stop(services)
        if code != 0:
            fail("the laptop recording run failed; fix it before replaying.")
        READY_PATH.write_text("recorded\n", encoding="utf-8")
        print("e2e_real: recordings saved; now running both sizes in replay mode.")
    failures = 0
    for project in ("laptop", "phone"):
        cmd_reset()
        services = [
            _start_api("chat", CHAT_PORT, {"AI_REPLAY": "replay"}),
            _start_api("learner", LEARNER_PORT, {"AI_REPLAY": "replay"}),
        ]
        try:
            _wait_for_health(CHAT_PORT)
            _wait_for_health(LEARNER_PORT)
            code = _run_playwright(project)
        finally:
            _stop(services)
        if code != 0:
            failures += 1
            print(f"e2e_real: {project} failed; stopping.")
            break
    minutes = (time.monotonic() - started) / 60
    print(f"e2e_real: done in {minutes:.1f} minutes.")
    if failures:
        raise SystemExit(1)
    if not READY_PATH.is_file():
        print(
            "e2e_real: journeys skipped for missing recordings; "
            "run with --record (needs your yes) to record them."
        )


def cmd_serve() -> None:
    """Reset, then run both APIs in replay mode until Ctrl+C."""
    cmd_reset()
    services = [
        _start_api("chat", CHAT_PORT, {"AI_REPLAY": "replay"}),
        _start_api("learner", LEARNER_PORT, {"AI_REPLAY": "replay"}),
    ]
    try:
        _wait_for_health(CHAT_PORT)
        _wait_for_health(LEARNER_PORT)
        print(
            f"e2e_real: chat on http://localhost:{CHAT_PORT}, "
            f"learner on http://localhost:{LEARNER_PORT} (Ctrl+C stops)."
        )
        while True:
            time.sleep(1)
            if any(service.poll() is not None for service in services):
                fail("an API stopped unexpectedly.")
    except KeyboardInterrupt:
        pass
    finally:
        _stop(services)


def main(argv: list | None = None) -> None:
    parser = argparse.ArgumentParser(description="The real-mode screen-test runner.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("save", help="dump our database for the journeys (you, once)")
    sub.add_parser("reset", help="rebuild the throwaway database from the dump")
    run_parser = sub.add_parser("run", help="reset, run the journeys, stop")
    run_parser.add_argument(
        "--record",
        action="store_true",
        help="record fresh replies at laptop size first (spends about $5-15)",
    )
    sub.add_parser("serve", help="both APIs in replay mode until Ctrl+C")
    args = parser.parse_args(argv)
    if args.command == "save":
        cmd_save()
    elif args.command == "reset":
        cmd_reset()
    elif args.command == "run":
        cmd_run(args.record)
    elif args.command == "serve":
        cmd_serve()


if __name__ == "__main__":
    main()
